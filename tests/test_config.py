"""Pruebas de la configuración."""

from __future__ import annotations

import pytest

from vuelos.config import Config, ConfigInvalida

MINIMA = {
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "TELEGRAM_CHATS_AUTORIZADOS": "111,222",
}


def _entorno(monkeypatch, **extra):
    for clave in list(MINIMA) + [
        "MERCADO", "MONEDA", "IDIOMA", "INTERVALO_SONDEO_HORAS", "JITTER_MAXIMO_MINUTOS",
        "UMBRAL_BAJADA_PORCENTAJE", "MAX_BUSQUEDAS_ACTIVAS", "HORA_RESUMEN", "ZONA_HORARIA",
        "RUTA_BD", "RUTA_LOGS", "SONDEOS_FALLIDOS_PARA_MARCAR_FALLIDA", "BLOQUES_EN_SEGUIMIENTO",
    ]:
        monkeypatch.delenv(clave, raising=False)
    for clave, valor in {**MINIMA, **extra}.items():
        monkeypatch.setenv(clave, valor)


def test_arranca_con_lo_minimo_y_aplica_defectos(monkeypatch):
    _entorno(monkeypatch)
    c = Config.desde_entorno()
    assert c.telegram_token == "123:abc"
    assert c.chats_autorizados == (111, 222)
    assert c.mercado == "CO"
    assert c.moneda == "USD"
    assert c.intervalo_sondeo_horas == 4
    assert c.umbral_bajada_porcentaje == 5
    assert c.hora_resumen.hour == 8


def test_sin_token_no_arranca(monkeypatch):
    _entorno(monkeypatch)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    with pytest.raises(ConfigInvalida, match="TELEGRAM_BOT_TOKEN"):
        Config.desde_entorno()


def test_sin_chats_autorizados_no_arranca(monkeypatch):
    _entorno(monkeypatch)
    monkeypatch.delenv("TELEGRAM_CHATS_AUTORIZADOS")
    with pytest.raises(ConfigInvalida, match="CHATS_AUTORIZADOS"):
        Config.desde_entorno()


def test_umbral_fuera_de_rango(monkeypatch):
    _entorno(monkeypatch, UMBRAL_BAJADA_PORCENTAJE="0")
    with pytest.raises(ConfigInvalida, match="UMBRAL"):
        Config.desde_entorno()


def test_jitter_no_puede_superar_el_intervalo(monkeypatch):
    _entorno(monkeypatch, INTERVALO_SONDEO_HORAS="1", JITTER_MAXIMO_MINUTOS="60")
    with pytest.raises(ConfigInvalida, match="JITTER"):
        Config.desde_entorno()


def test_zona_horaria_desconocida(monkeypatch):
    _entorno(monkeypatch, ZONA_HORARIA="Marte/Olympus")
    with pytest.raises(ConfigInvalida, match="ZONA_HORARIA"):
        Config.desde_entorno()


def test_el_token_no_aparece_en_el_codigo():
    """El secreto entra por entorno; que no se cuele un valor por defecto."""
    from pathlib import Path
    fuente = Path("src/vuelos/config.py").read_text(encoding="utf-8")
    assert "123:abc" not in fuente
    assert 'TELEGRAM_BOT_TOKEN") or ""' in fuente
