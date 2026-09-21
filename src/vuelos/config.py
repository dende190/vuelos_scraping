"""Configuración del sistema, leída de variables de entorno.

Ningún secreto vive en el código: todo entra por entorno o por un fichero
`.env` que no se versiona. Ver `.env.example` para la lista completa.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


class ConfigInvalida(Exception):
    """La configuración no permite arrancar."""


def _entero(nombre: str, por_defecto: int) -> int:
    bruto = os.getenv(nombre)
    if bruto is None or bruto.strip() == "":
        return por_defecto
    try:
        return int(bruto)
    except ValueError as exc:
        raise ConfigInvalida(f"{nombre} debe ser un entero, no {bruto!r}") from exc


def _hora(nombre: str, por_defecto: str) -> time:
    bruto = (os.getenv(nombre) or por_defecto).strip()
    try:
        horas, minutos = bruto.split(":")
        return time(int(horas), int(minutos))
    except ValueError as exc:
        raise ConfigInvalida(f"{nombre} debe tener formato HH:MM, no {bruto!r}") from exc


def _lista_enteros(nombre: str) -> list[int]:
    bruto = (os.getenv(nombre) or "").strip()
    if not bruto:
        return []
    try:
        return [int(parte.strip()) for parte in bruto.split(",") if parte.strip()]
    except ValueError as exc:
        raise ConfigInvalida(
            f"{nombre} debe ser una lista de identificadores numéricos separados por coma"
        ) from exc


@dataclass(frozen=True)
class Config:
    """Configuración completa, ya validada."""

    telegram_token: str
    chats_autorizados: tuple[int, ...]

    mercado: str
    moneda: str
    idioma: str

    intervalo_sondeo_horas: int
    jitter_maximo_minutos: int
    umbral_bajada_porcentaje: int
    max_busquedas_activas: int
    sondeos_fallidos_para_marcar_fallida: int
    bloques_en_seguimiento: int

    hora_resumen: time
    zona_horaria: ZoneInfo

    ruta_bd: Path
    ruta_logs: Path

    errores: tuple[str, ...] = field(default=())

    @classmethod
    def desde_entorno(cls, ruta_env: Path | None = None) -> Config:
        """Construye la configuración desde el entorno.

        Lanza `ConfigInvalida` si falta algo sin lo que el bot no puede operar.
        """
        load_dotenv(ruta_env, override=False)

        token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            raise ConfigInvalida(
                "Falta TELEGRAM_BOT_TOKEN. Copia .env.example a .env y pon la credencial "
                "que te dio @BotFather."
            )

        chats = _lista_enteros("TELEGRAM_CHATS_AUTORIZADOS")
        if not chats:
            raise ConfigInvalida(
                "Falta TELEGRAM_CHATS_AUTORIZADOS. Sin chats autorizados el bot no "
                "respondería a nadie."
            )

        zona = (os.getenv("ZONA_HORARIA") or "America/Bogota").strip()
        try:
            tz = ZoneInfo(zona)
        except Exception as exc:
            raise ConfigInvalida(f"ZONA_HORARIA desconocida: {zona!r}") from exc

        umbral = _entero("UMBRAL_BAJADA_PORCENTAJE", 5)
        if not 0 < umbral < 100:
            raise ConfigInvalida("UMBRAL_BAJADA_PORCENTAJE debe estar entre 1 y 99")

        intervalo = _entero("INTERVALO_SONDEO_HORAS", 4)
        if intervalo < 1:
            raise ConfigInvalida("INTERVALO_SONDEO_HORAS debe ser al menos 1")

        jitter = _entero("JITTER_MAXIMO_MINUTOS", 20)
        if jitter < 0 or jitter >= intervalo * 60:
            raise ConfigInvalida(
                "JITTER_MAXIMO_MINUTOS debe ser positivo y menor que el intervalo de sondeo"
            )

        return cls(
            telegram_token=token,
            chats_autorizados=tuple(chats),
            mercado=(os.getenv("MERCADO") or "CO").strip().upper(),
            moneda=(os.getenv("MONEDA") or "USD").strip().upper(),
            idioma=(os.getenv("IDIOMA") or "es").strip(),
            intervalo_sondeo_horas=intervalo,
            jitter_maximo_minutos=jitter,
            umbral_bajada_porcentaje=umbral,
            max_busquedas_activas=_entero("MAX_BUSQUEDAS_ACTIVAS", 5),
            sondeos_fallidos_para_marcar_fallida=_entero(
                "SONDEOS_FALLIDOS_PARA_MARCAR_FALLIDA", 3
            ),
            bloques_en_seguimiento=_entero("BLOQUES_EN_SEGUIMIENTO", 3),
            hora_resumen=_hora("HORA_RESUMEN", "08:00"),
            zona_horaria=tz,
            ruta_bd=Path(os.getenv("RUTA_BD") or "./datos/vuelos.db").expanduser(),
            ruta_logs=Path(os.getenv("RUTA_LOGS") or "./datos/logs").expanduser(),
        )
