"""Contrato común de las fuentes de precios.

El resto del sistema habla con este contrato y nunca con una fuente concreta.
Esa es la única protección real del proyecto: las fuentes no son oficiales y
van a cambiar, y cambiar de fuente debe ser sustituir un adaptador.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from vuelos.modelos import Etiqueta, Filtros


class ErrorProveedor(Exception):
    """La fuente no pudo responder. El sondeo continúa con las demás."""


class LimiteDePeticiones(ErrorProveedor):
    """La fuente pide bajar el ritmo. Se reintenta con esperas crecientes."""


class MercadoIncorrecto(ErrorProveedor):
    """La fuente no aplicó el mercado pedido.

    Se trata como error y no como aviso: un precio de otro mercado es
    plausible pero impagable para el usuario, y aceptarlo sería el fallo más
    caro del sistema, porque no tiene ningún síntoma visible.
    """


@dataclass(frozen=True)
class Consulta:
    """Búsqueda de un par de fechas concreto."""

    origen: str
    destino: str
    salida: date
    regreso: date
    mercado: str
    moneda: str
    filtros: Filtros = field(default_factory=Filtros)

    def __post_init__(self) -> None:
        if self.regreso < self.salida:
            raise ValueError("el regreso no puede ser anterior a la salida")


@dataclass(frozen=True)
class ConsultaVentana:
    """Búsqueda de todos los bloques de N noches dentro de una ventana.

    Cada adaptador la resuelve como pueda: Kiwi de una vez, Google bloque a
    bloque. Quien la invoca no necesita saber cuántas peticiones costó.
    """

    origen: str
    destino: str
    ventana_ini: date
    ventana_fin: date
    duracion_noches: int
    mercado: str
    moneda: str
    filtros: Filtros = field(default_factory=Filtros)

    def __post_init__(self) -> None:
        if self.ventana_fin < self.ventana_ini:
            raise ValueError("la ventana termina antes de empezar")
        if self.duracion_noches < 1:
            raise ValueError("la duración debe ser de al menos una noche")
        if self.duracion_noches > self.dias_de_ventana:
            raise ValueError(
                f"una duración de {self.duracion_noches} noches no cabe en una ventana "
                f"de {self.dias_de_ventana} días"
            )

    @property
    def dias_de_ventana(self) -> int:
        return (self.ventana_fin - self.ventana_ini).days

    def bloques(self) -> list[tuple[date, date]]:
        """Los bloques posibles, para los adaptadores que consulten uno a uno."""
        from datetime import timedelta

        duracion = timedelta(days=self.duracion_noches)
        bloques = []
        salida = self.ventana_ini
        while salida + duracion <= self.ventana_fin:
            bloques.append((salida, salida + duracion))
            salida += timedelta(days=1)
        return bloques


@dataclass(frozen=True)
class Resultado:
    """Un itinerario devuelto por una fuente, ya normalizado.

    `moneda` es la que devolvió la fuente; la conversión a la moneda de
    referencia se hace fuera, para que el adaptador no tenga que saber nada de
    tipos de cambio.
    """

    salida: date
    regreso: date
    precio: float
    moneda: str
    mercado: str
    escalas: int
    aerolineas: tuple[str, ...] = ()
    etiquetas: frozenset[Etiqueta] = field(default_factory=frozenset)
    enlace: str | None = None
    obtenido_en: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "etiquetas", frozenset(self.etiquetas))
        object.__setattr__(self, "aerolineas", tuple(self.aerolineas))
        if self.enlace is None:
            object.__setattr__(
                self, "etiquetas", self.etiquetas | {Etiqueta.NO_VERIFICABLE}
            )

    def cumple(self, filtros: Filtros) -> bool:
        """Si este resultado respeta los filtros duros de la búsqueda.

        Se aplica antes de que el precio entre en el histórico: un resultado
        que incumple no debe poder disparar una alerta.
        """
        if filtros.max_escalas is not None and self.escalas > filtros.max_escalas:
            return False
        if filtros.requiere_maleta and Etiqueta.SIN_EQUIPAJE_FACTURADO in self.etiquetas:
            return False
        if filtros.aerolineas:
            permitidas = {a.upper() for a in filtros.aerolineas}
            if not permitidas & {a.upper() for a in self.aerolineas}:
                return False
        return True


class Proveedor(ABC):
    """Una fuente de precios."""

    #: Identificador estable. Es la clave de la serie histórica, así que
    #: cambiarlo rompe la continuidad del histórico.
    nombre: str

    @abstractmethod
    def buscar(self, consulta: Consulta) -> list[Resultado]:
        """Itinerarios para un par de fechas concreto."""

    @abstractmethod
    def buscar_ventana(self, consulta: ConsultaVentana) -> list[Resultado]:
        """Itinerarios de todos los bloques que caben en la ventana."""

    @abstractmethod
    def peticiones_por_ventana(self, consulta: ConsultaVentana) -> int:
        """Cuántas peticiones de red cuesta resolver esa ventana.

        Lo usa el planificador para decidir si puede repetirla en cada sondeo
        o si necesita barrido diario más seguimiento acotado.
        """
