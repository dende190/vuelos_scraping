"""Modelos del dominio."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum


class Modo(StrEnum):
    """Cómo se expresan las fechas de una búsqueda."""

    EXACTAS = "A"
    VENTANA = "B"


class Estado(StrEnum):
    """Estados posibles de una búsqueda. Solo `ACTIVA` genera consultas."""

    ACTIVA = "activa"
    PAUSADA = "pausada"
    TERMINADA = "terminada_por_usuario"
    VENCIDA = "vencida"
    FALLIDA = "fallida"

    @property
    def es_final(self) -> bool:
        return self in (Estado.TERMINADA, Estado.VENCIDA, Estado.FALLIDA)


class Franja(StrEnum):
    """Franja horaria de salida preferida."""

    MANANA = "manana"
    TARDE = "tarde"
    NOCHE = "noche"


class Etiqueta(StrEnum):
    """Advertencias sobre un resultado que afectan a su comparabilidad.

    El valor coincide con el nombre de su columna en la tabla `precios`.
    """

    BILLETES_SEPARADOS = "billetes_separados"
    SIN_EQUIPAJE_FACTURADO = "sin_equipaje_facturado"
    NO_VERIFICABLE = "no_verificable"
    CIUDAD_OCULTA = "ciudad_oculta"
    BILLETE_DESECHADO = "billete_desechado"


class Motivo(StrEnum):
    """Por qué se envió una notificación."""

    REFERENCIA_INICIAL = "referencia_inicial"
    BAJADA = "bajada"
    CIERRE = "cierre"


def a_utc(momento: datetime | None, *, campo: str) -> datetime | None:
    """Normaliza un instante a UTC, rechazando los que no llevan zona horaria.

    Un `datetime` sin zona es ambiguo: no se sabe si son las 11:39 de Bogotá o
    de Londres. Adivinar produce desfases silenciosos de horas, y compararlo
    después contra un instante con zona lanza TypeError. Es preferible fallar
    aquí, donde el error se ve, que al reactivar una búsqueda pausada.
    """
    if momento is None:
        return None
    if momento.tzinfo is None or momento.utcoffset() is None:
        raise ValueError(
            f"{campo} llegó sin zona horaria ({momento.isoformat()}). "
            "Usa datetime.now(UTC) o añade tzinfo explícito."
        )
    return momento.astimezone(UTC)


@dataclass(frozen=True)
class Filtros:
    """Filtros que acotan qué resultados cuentan para una búsqueda.

    Conjunto cerrado: cada campo es una columna. `None` significa sin
    restricción.
    """

    max_escalas: int | None = None
    max_escala_minutos: int | None = None
    requiere_maleta: bool = False
    franja_horaria: Franja | None = None
    aerolineas: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_escalas is not None and self.max_escalas < 0:
            raise ValueError("max_escalas no puede ser negativo")
        if self.max_escala_minutos is not None and self.max_escala_minutos <= 0:
            raise ValueError("max_escala_minutos debe ser positivo")

    @property
    def vacios(self) -> bool:
        return self == Filtros()


@dataclass(frozen=True)
class Busqueda:
    """Una búsqueda vigilada."""

    chat_id: int
    origen: str
    destino: str
    modo: Modo
    salida: date | None = None
    regreso: date | None = None
    ventana_ini: date | None = None
    ventana_fin: date | None = None
    duracion_noches: int | None = None
    filtros: Filtros = field(default_factory=Filtros)
    estado: Estado = Estado.ACTIVA
    pausada_hasta: datetime | None = None
    sondeos_fallidos: int = 0
    id: int | None = None
    creada_en: datetime | None = None
    actualizada_en: datetime | None = None

    def __post_init__(self) -> None:
        if self.modo is Modo.EXACTAS:
            if self.salida is None or self.regreso is None:
                raise ValueError("el modo de fechas exactas exige salida y regreso")
            if self.regreso < self.salida:
                raise ValueError("el regreso no puede ser anterior a la salida")
        else:
            faltan = self.ventana_ini is None or self.ventana_fin is None
            if faltan or self.duracion_noches is None:
                raise ValueError("el modo de ventana exige ventana_ini, ventana_fin y duración")
            if self.ventana_fin < self.ventana_ini:
                raise ValueError("la ventana termina antes de empezar")
            if self.duracion_noches < 1:
                raise ValueError("la duración debe ser de al menos una noche")
            dias = (self.ventana_fin - self.ventana_ini).days
            if self.duracion_noches > dias:
                raise ValueError(
                    f"una duración de {self.duracion_noches} noches no cabe en una ventana "
                    f"de {dias} días; el máximo es {dias}"
                )
        # Los instantes se guardan en UTC. Se valida aquí para que una fecha sin
        # zona no llegue nunca a la base.
        object.__setattr__(self, "pausada_hasta", a_utc(self.pausada_hasta, campo="pausada_hasta"))


@dataclass(frozen=True)
class Precio:
    """Un precio observado en una fuente, para un bloque de fechas concreto."""

    busqueda_id: int
    fuente: str
    salida: date
    regreso: date
    precio: float
    moneda: str
    precio_ref: float
    moneda_ref: str
    mercado: str
    cambio_aplicado: float = 1.0
    escalas: int | None = None
    aerolineas: list[str] = field(default_factory=list)
    etiquetas: frozenset[Etiqueta] = field(default_factory=frozenset)
    enlace: str | None = None
    obtenido_en: datetime | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "etiquetas", frozenset(self.etiquetas))
        object.__setattr__(self, "obtenido_en", a_utc(self.obtenido_en, campo="obtenido_en"))

    def tiene(self, etiqueta: Etiqueta) -> bool:
        return etiqueta in self.etiquetas
