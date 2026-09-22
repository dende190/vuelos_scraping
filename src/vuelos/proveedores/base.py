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
    """Búsqueda de todas las estancias de N noches dentro de una ventana.

    **`duracion_noches` son noches EN DESTINO**, contadas desde que se llega
    hasta que se despega de vuelta. No son días entre despegues: con un vuelo
    nocturno que sale el 17 a las 15:55 y aterriza el 18 a las 00:24, volver
    el 23 son cinco noches, no seis. Es la lectura natural de "quiero estar
    doce días allá" y la que usa `nightsCount` de Kiwi.

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
                f"una estancia de {self.duracion_noches} noches no cabe en una ventana "
                f"de {self.dias_de_ventana} días"
            )

    @property
    def dias_de_ventana(self) -> int:
        return (self.ventana_fin - self.ventana_ini).days

    def bloques(self) -> list[tuple[date, date]]:
        """Pares de fechas de despegue a consultar, uno a uno.

        Solo lo necesitan los adaptadores que no admiten rangos de fechas.
        Como la duración son noches en destino y la fecha de llegada depende
        del vuelo, por cada fecha de salida hay dos regresos posibles: el que
        corresponde a llegar el mismo día y el de llegar al día siguiente.
        Se consultan los dos y después se descartan los que no cumplan las
        noches pedidas, porque la hora de llegada no se conoce de antemano.
        """
        from datetime import timedelta

        vistos: set[tuple[date, date]] = set()
        bloques: list[tuple[date, date]] = []
        salida = self.ventana_ini
        while salida <= self.ventana_fin:
            for dias_hasta_llegar in (0, 1):
                regreso = salida + timedelta(days=dias_hasta_llegar + self.duracion_noches)
                if regreso > self.ventana_fin:
                    continue
                par = (salida, regreso)
                if par not in vistos:
                    vistos.add(par)
                    bloques.append(par)
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
    #: Fecha de llegada a destino del vuelo de ida. Es lo que permite contar
    #: las noches reales en destino; con un vuelo nocturno no coincide con
    #: `salida`. `None` cuando la fuente no la informa.
    llegada_ida: date | None = None
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

    @property
    def noches_en_destino(self) -> int | None:
        """Noches reales entre la llegada y el despegue de vuelta."""
        if self.llegada_ida is None:
            return None
        return (self.regreso - self.llegada_ida).days

    def dura(self, noches: int) -> bool:
        """Si la estancia es la pedida.

        Cuando la fuente no informa de la llegada no se puede afirmar que no
        cumple, así que se acepta: descartarlo sería tirar un precio válido
        por un dato que falta.
        """
        reales = self.noches_en_destino
        return reales is None or reales == noches

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
