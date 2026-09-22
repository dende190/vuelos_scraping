"""Tarea 1.8: medir cada cuánto cambian de verdad los precios.

Contrasta el supuesto del que depende la decisión 6 de `design.md`: que las
tarifas se recargan pocas veces al día, y que por tanto sondear cada 4 horas
no pierde casi nada frente a sondear cada pocos minutos.

Los resultados se escriben en `datos/mediciones/`, DENTRO del repositorio. La
primera vez se dejaron en el directorio temporal del sistema y se perdieron al
purgarlo tres días después.

Uso:
    .venv/bin/python herramientas/medir_estabilidad.py [muestras] [minutos]
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "datos" / "mediciones" / "estabilidad-precios.jsonl"
CONSULTA_KIWI = Path(__file__).parent / "consulta_kiwi.graphql"

RUTA = ("BOG", "RDU")
IDA, VUELTA = "2026-11-20", "2026-12-04"
MERCADO, MONEDA = "CO", "USD"


def google() -> list[int]:
    from fast_flights import FlightQuery, Passengers, create_query
    from fast_flights.parser import parse
    from primp import Client

    q = create_query(
        flights=[FlightQuery(date=IDA, from_airport=RUTA[0], to_airport=RUTA[1]),
                 FlightQuery(date=VUELTA, from_airport=RUTA[1], to_airport=RUTA[0])],
        trip="round-trip", seat="economy",
        passengers=Passengers(adults=1), currency=MONEDA, language="es")
    # La libreria no envia gl; se inyecta a mano (ver design.md, fase 1).
    params = dict(q.params()) | {"gl": MERCADO}
    cliente = Client(impersonate="chrome_145", impersonate_os="macos",
                     referer=True, cookie_store=True)
    html = cliente.get("https://www.google.com/travel/flights", params=params).text
    return sorted(f.price for f in parse(html) if isinstance(f.price, int))


def kiwi() -> list[float]:
    variables = {
        "search": {
            "itinerary": {
                "source": {"ids": [f"Station:airport:{RUTA[0]}"]},
                "destination": {"ids": [f"Station:airport:{RUTA[1]}"]},
                "outboundDepartureDate": {"start": f"{IDA}T00:00:00", "end": f"{IDA}T23:59:59"},
                "inboundDepartureDate": {"start": f"{VUELTA}T00:00:00",
                                         "end": f"{VUELTA}T23:59:59"},
            },
            "passengers": {"adults": 1, "adultsHandBags": 1, "adultsHoldBags": 0},
            "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
        },
        "filter": {"limit": 8, "enableSelfTransfer": True,
                   "enableThrowAwayTicketing": False, "enableTrueHiddenCity": False},
        "options": {"currency": MONEDA.lower(), "locale": "es", "market": MERCADO.lower(),
                    "partner": "skypicker", "sortBy": "PRICE"},
    }
    cuerpo = json.dumps({"query": CONSULTA_KIWI.read_text(encoding="utf-8"),
                         "variables": variables}).encode()
    peticion = urllib.request.Request(
        "https://api.skypicker.com/umbrella/v2/graphql", data=cuerpo,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(peticion, timeout=120) as respuesta:
        datos = json.loads(respuesta.read())
    nodo = (datos.get("data", {}) or {}).get("returnItineraries") or {}
    return sorted(round(float(i["price"]["amount"]), 2) for i in nodo.get("itineraries") or [])


def main() -> None:
    muestras = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    minutos = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    for n in range(muestras):
        fila: dict = {"n": n, "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                      "ruta": "-".join(RUTA), "ida": IDA, "vuelta": VUELTA,
                      "mercado": MERCADO, "moneda": MONEDA}
        for nombre, funcion in (("google", google), ("kiwi", kiwi)):
            try:
                fila[nombre] = funcion()
            except Exception as exc:
                fila[nombre] = f"ERROR {type(exc).__name__}: {exc}"
        with SALIDA.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        print(fila, flush=True)
        if n < muestras - 1:
            time.sleep(minutos * 60)
    print("FIN")


if __name__ == "__main__":
    main()
