"""Pruebas de reintentos y conversión de moneda."""

from __future__ import annotations

import pytest

from vuelos.proveedores.base import ErrorProveedor, LimiteDePeticiones
from vuelos.proveedores.cambio import SinTipoDeCambio, convertir
from vuelos.proveedores.reintentos import con_reintentos


class _Reloj:
    """Registra las esperas en vez de dormirlas."""

    def __init__(self) -> None:
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


# ------------------------------------------------------------------ reintentos

def test_a_la_primera_no_espera():
    reloj = _Reloj()
    assert con_reintentos(lambda: 42, dormir=reloj) == 42
    assert reloj.esperas == []


def test_reintenta_y_acaba_saliendo_bien():
    reloj = _Reloj()
    intentos = {"n": 0}

    def operacion():
        intentos["n"] += 1
        if intentos["n"] < 3:
            raise LimiteDePeticiones("frena")
        return "ok"

    assert con_reintentos(operacion, dormir=reloj, aleatorio=lambda: 0.0) == "ok"
    assert intentos["n"] == 3
    assert len(reloj.esperas) == 2


def test_las_esperas_crecen():
    reloj = _Reloj()
    with pytest.raises(LimiteDePeticiones):
        con_reintentos(
            lambda: (_ for _ in ()).throw(LimiteDePeticiones("frena")),
            intentos=4, dormir=reloj, aleatorio=lambda: 0.0)
    assert reloj.esperas == sorted(reloj.esperas)
    assert reloj.esperas[-1] > reloj.esperas[0]


def test_no_espera_despues_del_ultimo_intento():
    reloj = _Reloj()
    with pytest.raises(ErrorProveedor):
        con_reintentos(
            lambda: (_ for _ in ()).throw(ErrorProveedor("caida")),
            intentos=3, dormir=reloj, aleatorio=lambda: 0.0)
    assert len(reloj.esperas) == 2


def test_el_limite_de_peticiones_espera_mas_que_un_error_normal():
    lento, rapido = _Reloj(), _Reloj()
    for excepcion, reloj in ((LimiteDePeticiones("x"), lento), (ErrorProveedor("x"), rapido)):
        with pytest.raises(ErrorProveedor):
            con_reintentos(lambda e=excepcion: (_ for _ in ()).throw(e),
                           intentos=2, dormir=reloj, aleatorio=lambda: 0.0)
    assert lento.esperas[0] > rapido.esperas[0]


def test_un_error_ajeno_a_la_fuente_no_se_reintenta():
    reloj = _Reloj()
    with pytest.raises(ZeroDivisionError):
        con_reintentos(lambda: 1 / 0, dormir=reloj)
    assert reloj.esperas == []


# -------------------------------------------------------------------- cambio

def test_misma_moneda_no_convierte():
    c = convertir(631.0, "USD", "USD")
    assert c.importe == 631.0 and c.cambio_aplicado == 1.0


def test_convierte_con_la_fuente_dada():
    c = convertir(680.0, "USD", "COP", fuente=lambda o, d: 3159.76)
    assert c.moneda == "COP"
    assert c.cambio_aplicado == 3159.76
    assert c.importe == pytest.approx(2148636.8)


def test_sin_fuente_falla_en_vez_de_estimar():
    with pytest.raises(SinTipoDeCambio, match="no hay fuente"):
        convertir(680.0, "USD", "COP")


def test_tipo_invalido_falla():
    with pytest.raises(SinTipoDeCambio, match="inválido"):
        convertir(680.0, "USD", "COP", fuente=lambda o, d: 0.0)
