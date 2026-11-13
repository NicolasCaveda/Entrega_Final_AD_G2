#!/usr/bin/env python
"""
test_credito_y_verdes.py — Tests de la prima por espacios verdes y de los
aptos para credito (credito_y_verdes.py). Sin datos del pipeline.

Oraculos independientes:
  - una prima plantada en datos sinteticos: el tramo cercano tiene que
    recuperarla y su intervalo tiene que contenerla
  - el barrio fijo: si los barrios caros estan cerca de las plazas, sin
    barrio la prima se confundiria con el barrio; con barrio, no
con NEGATIVOS: sin prima plantada, el intervalo incluye el cero.

Uso:
    py src/test_credito_y_verdes.py
"""

import sys

import numpy as np
import pandas as pd

import credito_y_verdes as CV
import supuestos as S
from fuentes_externas import Reporte

fallos = []
corridos = 0


def check(descripcion: str, condicion: bool, detalle: str = "") -> None:
    global corridos
    corridos += 1
    if not condicion:
        fallos.append(descripcion + (f"\n      {detalle}" if detalle else ""))


def sintetico(prima: float, semilla: int) -> pd.DataFrame:
    """Ventas de 30 barrios; los barrios caros tienen las plazas mas cerca."""
    rng = np.random.default_rng(semilla)
    n = 6_000
    barrio = rng.integers(0, 30, n)
    nivel = barrio / 30                                     # efecto del barrio sobre log(m2)
    dist = rng.uniform(0, 900, n) * (1.2 - nivel)          # barrios caros, plazas mas cerca
    y = 7.5 + nivel + np.log1p(prima) * (dist < 150) + rng.normal(0, 0.15, n)
    return pd.DataFrame({
        "barrio": [f"b{b}" for b in barrio], "tipo_familia": "departamento", "y": y,
        "dist_plaza_m": dist, "dist_transporte_m": rng.uniform(0, 1500, n),
        "log_sup": rng.normal(4, 0.3, n), "antiguedad_anios": rng.uniform(0, 60, n),
        "a_reciclar": 0, "amenities": rng.integers(0, 2, n), "cochera_txt": rng.integers(0, 2, n)})


con = CV.prima_verde(sintetico(0.06, 3), "dist_plaza_m", S.TRAMOS_PLAZA_M, True).set_index("tramo_m")
cerca = con.iloc[0]
check("prima plantada de 6%: el tramo cercano la recupera", abs(cerca["efecto_pct"] - 6.0) < 1.5,
      f"{cerca['efecto_pct']:.2f}")
check("prima plantada: el intervalo la contiene", cerca["ic_inf"] < 6.0 < cerca["ic_sup"],
      f"[{cerca['ic_inf']:.2f}, {cerca['ic_sup']:.2f}]")
check("prima plantada: el intervalo excluye el cero", cerca["ic_inf"] > 0)
check("los tramos sin prima no la muestran", (con.iloc[1:-1]["efecto_pct"].abs() < 1.5).all(),
      f"{con.iloc[1:-1]['efecto_pct'].round(2).to_dict()}")
check("el tramo lejano es la referencia, en 0", con.iloc[-1]["efecto_pct"] == 0.0 and np.isnan(con.iloc[-1]["ic_inf"]))
check("cada tramo informa sus avisos", int(con["n"].sum()) == 6_000)

sin = CV.prima_verde(sintetico(0.0, 4), "dist_plaza_m", S.TRAMOS_PLAZA_M, True).iloc[0]
check("NEG: sin prima plantada, el intervalo incluye el cero", sin["ic_inf"] < 0 < sin["ic_sup"],
      f"[{sin['ic_inf']:.2f}, {sin['ic_sup']:.2f}]")
# NEG: el mismo dato sin barrio fijo confunde barrio con plaza (la prima sale inflada).
d = sintetico(0.0, 4)
sin_barrio = np.polyfit((d["dist_plaza_m"] < 150).astype(float), d["y"], 1)[0]
check("NEG: sin barrio fijo, la cercania parece valer aunque no se planto nada", sin_barrio > 0.05,
      f"{sin_barrio:.3f}")

# Credito: proporciones contra el conteo directo.
v = pd.DataFrame({"operacion": ["venta"] * 8, "venta_usd": [90_000.0] * 8, "venta_m2_usd": [2_000.0] * 8,
                  "apto_credito": [1, 1, 0, 0, 0, 0, 0, 1], "tipo_familia": "departamento",
                  "barrio": "x", "superficie_rango": "36-55",
                  "universo_decision": [True] * 4 + [False] * 4, "p1_comprar": [True, False] * 4,
                  "p1_comprar_con_entrada": [False] * 8})
rep = Reporte()
import contextlib, io
with contextlib.redirect_stdout(io.StringIO()):
    filas = {f["medida"]: f["valor"] for f in CV.credito(v, rep)}
check("credito: proporcion en las ventas", filas["proporcion apto credito: ventas"] == 37.5)
check("credito: proporcion en el universo", filas["proporcion apto credito: universo de la decision"] == 50.0)

print(f"Tests corridos : {corridos}")
print(f"Fallos         : {len(fallos)}")
if fallos:
    print()
    for f in fallos:
        print(f"  FALLO: {f}")
    sys.exit(1)
print("OK")
sys.exit(0)
