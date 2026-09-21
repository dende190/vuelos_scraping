"""Acceso a datos de búsquedas, precios y notificaciones."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, date, datetime

from vuelos.modelos import (
    Busqueda,
    Estado,
    Etiqueta,
    Filtros,
    Franja,
    Modo,
    Motivo,
    Precio,
    a_utc,
)

# Columnas explícitas en vez de *, para que la consulta documente qué contrato
# espera el mapeador y un cambio de esquema salte al leer el código.
COLS_BUSQUEDA = (
    "id, chat_id, origen, destino, modo, salida, regreso, ventana_ini, ventana_fin, "
    "duracion_noches, max_escalas, max_escala_minutos, requiere_maleta, franja_horaria, "
    "estado, pausada_hasta, sondeos_fallidos, creada_en, actualizada_en"
)
COLS_PRECIO = (
    "id, busqueda_id, fuente, salida, regreso, precio, moneda, precio_ref, moneda_ref, "
    "cambio_aplicado, mercado, escalas, billetes_separados, sin_equipaje_facturado, "
    "no_verificable, ciudad_oculta, billete_desechado, aerolineas, enlace, obtenido_en"
)


def _ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _fecha(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor else None


def _momento(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


class Repositorio:
    """Operaciones de persistencia. Una instancia por proceso."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # ---------------------------------------------------------------- búsquedas

    def crear_busqueda(self, b: Busqueda) -> Busqueda:
        ahora = _ahora()
        f = b.filtros
        cur = self.con.execute(
            """
            INSERT INTO busquedas (chat_id, origen, destino, modo, salida, regreso,
                                   ventana_ini, ventana_fin, duracion_noches,
                                   max_escalas, max_escala_minutos, requiere_maleta,
                                   franja_horaria, estado, pausada_hasta, sondeos_fallidos,
                                   creada_en, actualizada_en)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                b.chat_id, b.origen, b.destino, str(b.modo),
                b.salida.isoformat() if b.salida else None,
                b.regreso.isoformat() if b.regreso else None,
                b.ventana_ini.isoformat() if b.ventana_ini else None,
                b.ventana_fin.isoformat() if b.ventana_fin else None,
                b.duracion_noches,
                f.max_escalas, f.max_escala_minutos, int(f.requiere_maleta),
                str(f.franja_horaria) if f.franja_horaria else None,
                str(b.estado),
                b.pausada_hasta.isoformat() if b.pausada_hasta else None,
                b.sondeos_fallidos, ahora, ahora,
            ),
        )
        busqueda_id = int(cur.lastrowid)
        self._guardar_aerolineas(busqueda_id, f.aerolineas)
        return self.obtener_busqueda(busqueda_id)

    def _guardar_aerolineas(self, busqueda_id: int, aerolineas: Iterable[str]) -> None:
        self.con.execute("DELETE FROM busqueda_aerolineas WHERE busqueda_id = ?", (busqueda_id,))
        self.con.executemany(
            "INSERT INTO busqueda_aerolineas (busqueda_id, aerolinea) VALUES (?,?)",
            [(busqueda_id, a) for a in aerolineas],
        )

    def _aerolineas_de(self, busqueda_id: int) -> tuple[str, ...]:
        filas = self.con.execute(
            "SELECT aerolinea FROM busqueda_aerolineas WHERE busqueda_id = ? ORDER BY aerolinea",
            (busqueda_id,),
        )
        return tuple(f["aerolinea"] for f in filas)

    def obtener_busqueda(self, busqueda_id: int) -> Busqueda | None:
        fila = self.con.execute(
            f"SELECT {COLS_BUSQUEDA} FROM busquedas WHERE id = ?", (busqueda_id,)
        ).fetchone()
        return self._a_busqueda(fila) if fila else None

    def listar_busquedas(self, chat_id: int, *, solo_vivas: bool = True) -> list[Busqueda]:
        sql = f"SELECT {COLS_BUSQUEDA} FROM busquedas WHERE chat_id = ?"
        if solo_vivas:
            sql += " AND estado IN ('activa', 'pausada')"
        sql += " ORDER BY creada_en"
        return [self._a_busqueda(f) for f in self.con.execute(sql, (chat_id,))]

    def listar_activas(self) -> list[Busqueda]:
        """Las únicas que deben generar consultas a las fuentes."""
        filas = self.con.execute(
            f"SELECT {COLS_BUSQUEDA} FROM busquedas WHERE estado = 'activa' ORDER BY id"
        )
        return [self._a_busqueda(f) for f in filas]

    def contar_activas(self, chat_id: int) -> int:
        fila = self.con.execute(
            "SELECT COUNT(*) AS n FROM busquedas WHERE chat_id = ? AND estado = 'activa'",
            (chat_id,),
        ).fetchone()
        return int(fila["n"])

    def cambiar_estado(
        self, busqueda_id: int, estado: Estado, *, pausada_hasta: datetime | None = None
    ) -> None:
        hasta = a_utc(pausada_hasta, campo="pausada_hasta")
        self.con.execute(
            "UPDATE busquedas SET estado = ?, pausada_hasta = ?, actualizada_en = ? WHERE id = ?",
            (str(estado), hasta.isoformat() if hasta else None, _ahora(), busqueda_id),
        )

    def registrar_sondeo_fallido(self, busqueda_id: int) -> int:
        """Suma uno al contador y devuelve el total acumulado."""
        self.con.execute(
            "UPDATE busquedas SET sondeos_fallidos = sondeos_fallidos + 1, "
            "actualizada_en = ? WHERE id = ?",
            (_ahora(), busqueda_id),
        )
        fila = self.con.execute(
            "SELECT sondeos_fallidos AS n FROM busquedas WHERE id = ?", (busqueda_id,)
        ).fetchone()
        return int(fila["n"])

    def reiniciar_sondeos_fallidos(self, busqueda_id: int) -> None:
        self.con.execute(
            "UPDATE busquedas SET sondeos_fallidos = 0, actualizada_en = ? WHERE id = ?",
            (_ahora(), busqueda_id),
        )

    def borrar_busqueda(self, busqueda_id: int) -> None:
        """Borrado explícito: se lleva también el histórico de precios."""
        self.con.execute("DELETE FROM busquedas WHERE id = ?", (busqueda_id,))

    # ------------------------------------------------------------------ precios

    def registrar_precio(self, p: Precio) -> int:
        cur = self.con.execute(
            """
            INSERT INTO precios (busqueda_id, fuente, salida, regreso, precio, moneda,
                                 precio_ref, moneda_ref, cambio_aplicado, mercado, escalas,
                                 billetes_separados, sin_equipaje_facturado, no_verificable,
                                 ciudad_oculta, billete_desechado,
                                 aerolineas, enlace, obtenido_en)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                p.busqueda_id, p.fuente, p.salida.isoformat(), p.regreso.isoformat(),
                p.precio, p.moneda, p.precio_ref, p.moneda_ref, p.cambio_aplicado,
                p.mercado, p.escalas,
                int(p.tiene(Etiqueta.BILLETES_SEPARADOS)),
                int(p.tiene(Etiqueta.SIN_EQUIPAJE_FACTURADO)),
                int(p.tiene(Etiqueta.NO_VERIFICABLE)),
                int(p.tiene(Etiqueta.CIUDAD_OCULTA)),
                int(p.tiene(Etiqueta.BILLETE_DESECHADO)),
                json.dumps(p.aerolineas, ensure_ascii=False),
                p.enlace,
                (p.obtenido_en or datetime.now(UTC)).isoformat(timespec="seconds"),
            ),
        )
        return int(cur.lastrowid)

    @staticmethod
    def _sql_excluir(excluir: Iterable[Etiqueta]) -> str:
        """Condición SQL que descarta los precios con alguna de esas etiquetas.

        Es el motivo de que las etiquetas sean columnas y no JSON: con JSON
        habría que traer toda la serie y filtrar en Python.
        """
        return "".join(f" AND {etiqueta.value} = 0" for etiqueta in excluir)

    def minimo_historico(
        self, busqueda_id: int, fuente: str, *, excluir: Iterable[Etiqueta] = ()
    ) -> Precio | None:
        """El precio más bajo jamás visto en esta serie.

        La serie es (búsqueda, fuente): nunca se comparan fuentes entre sí.
        """
        fila = self.con.execute(
            f"SELECT {COLS_PRECIO} FROM precios WHERE busqueda_id = ? AND fuente = ?"
            f"{self._sql_excluir(excluir)} ORDER BY precio_ref ASC, obtenido_en ASC LIMIT 1",
            (busqueda_id, fuente),
        ).fetchone()
        return self._a_precio(fila) if fila else None

    def ultimo_precio(
        self, busqueda_id: int, fuente: str, *, excluir: Iterable[Etiqueta] = ()
    ) -> Precio | None:
        fila = self.con.execute(
            f"SELECT {COLS_PRECIO} FROM precios WHERE busqueda_id = ? AND fuente = ?"
            f"{self._sql_excluir(excluir)} ORDER BY obtenido_en DESC, id DESC LIMIT 1",
            (busqueda_id, fuente),
        ).fetchone()
        return self._a_precio(fila) if fila else None

    def mejor_bloque(
        self, busqueda_id: int, fuente: str, limite: int, *, excluir: Iterable[Etiqueta] = ()
    ) -> list[tuple[date, date]]:
        """Los bloques de fechas más baratos vistos, para el seguimiento frecuente."""
        filas = self.con.execute(
            f"""
            SELECT salida, regreso, MIN(precio_ref) AS mejor
            FROM precios WHERE busqueda_id = ? AND fuente = ?{self._sql_excluir(excluir)}
            GROUP BY salida, regreso ORDER BY mejor ASC LIMIT ?
            """,
            (busqueda_id, fuente, limite),
        )
        return [(date.fromisoformat(f["salida"]), date.fromisoformat(f["regreso"])) for f in filas]

    # ----------------------------------------------------------- notificaciones

    def ultimo_precio_notificado(self, busqueda_id: int, fuente: str) -> float | None:
        """Contra esto se evalúa el umbral, no contra el último precio registrado."""
        fila = self.con.execute(
            "SELECT precio_notificado FROM notificaciones "
            "WHERE busqueda_id = ? AND fuente = ? AND motivo IN ('referencia_inicial','bajada') "
            "ORDER BY enviada_en DESC, id DESC LIMIT 1",
            (busqueda_id, fuente),
        ).fetchone()
        return float(fila["precio_notificado"]) if fila else None

    def registrar_notificacion(
        self, busqueda_id: int, fuente: str, precio_ref: float, moneda_ref: str, motivo: Motivo
    ) -> None:
        self.con.execute(
            "INSERT INTO notificaciones (busqueda_id, fuente, precio_notificado, "
            "moneda_ref, motivo, enviada_en) VALUES (?,?,?,?,?,?)",
            (busqueda_id, fuente, precio_ref, moneda_ref, str(motivo), _ahora()),
        )

    # ------------------------------------------------------------ estado fuentes

    def marcar_fuente(self, fuente: str, *, operativa: bool) -> bool:
        """Registra el estado de una fuente. Devuelve True si cambió."""
        fila = self.con.execute(
            "SELECT operativa FROM estado_fuentes WHERE fuente = ?", (fuente,)
        ).fetchone()
        anterior = None if fila is None else bool(fila["operativa"])
        columna = "ultimo_ok" if operativa else "ultimo_fallo"
        self.con.execute(
            f"""
            INSERT INTO estado_fuentes (fuente, operativa, {columna})
            VALUES (?,?,?)
            ON CONFLICT(fuente) DO UPDATE SET operativa = excluded.operativa,
                                              {columna} = excluded.{columna}
            """,
            (fuente, int(operativa), _ahora()),
        )
        return anterior is not None and anterior != operativa

    def fuentes_caidas(self) -> list[str]:
        return [
            f["fuente"]
            for f in self.con.execute(
                "SELECT fuente FROM estado_fuentes WHERE operativa = 0 ORDER BY fuente"
            )
        ]

    # ------------------------------------------------------------------ mapeo

    def _a_busqueda(self, f: sqlite3.Row) -> Busqueda:
        filtros = Filtros(
            max_escalas=f["max_escalas"],
            max_escala_minutos=f["max_escala_minutos"],
            requiere_maleta=bool(f["requiere_maleta"]),
            franja_horaria=Franja(f["franja_horaria"]) if f["franja_horaria"] else None,
            aerolineas=self._aerolineas_de(f["id"]),
        )
        return Busqueda(
            id=f["id"], chat_id=f["chat_id"], origen=f["origen"], destino=f["destino"],
            modo=Modo(f["modo"]),
            salida=_fecha(f["salida"]), regreso=_fecha(f["regreso"]),
            ventana_ini=_fecha(f["ventana_ini"]), ventana_fin=_fecha(f["ventana_fin"]),
            duracion_noches=f["duracion_noches"],
            filtros=filtros,
            estado=Estado(f["estado"]),
            pausada_hasta=_momento(f["pausada_hasta"]),
            sondeos_fallidos=f["sondeos_fallidos"],
            creada_en=_momento(f["creada_en"]),
            actualizada_en=_momento(f["actualizada_en"]),
        )

    @staticmethod
    def _a_precio(f: sqlite3.Row) -> Precio:
        etiquetas = {e for e in Etiqueta if f[e.value]}
        return Precio(
            id=f["id"], busqueda_id=f["busqueda_id"], fuente=f["fuente"],
            salida=date.fromisoformat(f["salida"]), regreso=date.fromisoformat(f["regreso"]),
            precio=f["precio"], moneda=f["moneda"],
            precio_ref=f["precio_ref"], moneda_ref=f["moneda_ref"],
            cambio_aplicado=f["cambio_aplicado"], mercado=f["mercado"],
            escalas=f["escalas"],
            aerolineas=json.loads(f["aerolineas"]) if f["aerolineas"] else [],
            etiquetas=frozenset(etiquetas),
            enlace=f["enlace"], obtenido_en=_momento(f["obtenido_en"]),
        )
