#!/usr/bin/env python
"""
test_curva_on.py — Tests de la curva de ON (curva_on.py). No toca la red.

Oraculos independientes:
  - un bono bullet comprado a la par el dia de un cupon rinde su cupon
    (anual: igual; semestral: (1 + c/2)^2 - 1, la tasa efectiva)
  - la duration modificada de un cero cupon es t / (1 + r)
  - el cupon corrido a mitad del periodo es medio cupon
con NEGATIVOS: mas precio, menos TIR; y una ventana sin ON suficientes no
inventa una vara.

Uso:
    py src/test_curva_on.py
"""

import sys
from datetime import date

import numpy as np
import pandas as pd

import curva_on as K

fallos = []
corridos = 0


def check(descripcion: str, condicion: bool, detalle: str = "") -> None:
    global corridos
    corridos += 1
    if not condicion:
        fallos.append(descripcion + (f"\n      {detalle}" if detalle else ""))


hoy = date(2026, 3, 15)

# --- Cronograma -------------------------------------------------------------------
f, previo = K.cronograma(date(2031, 3, 15), 2, hoy)
check("cronograma semestral a 5 anios: 10 pagos", len(f) == 10, f"{len(f)}")
check("el ultimo pago es el vencimiento", f[-1] == date(2031, 3, 15))
check("el cupon previo es el de hoy (fecha de pago)", previo == hoy, f"{previo}")
f, _ = K.cronograma(date(2028, 1, 31), 4, date(2026, 11, 13))
check("fin de mes: noviembre no tiene 31 y no rompe", all(isinstance(x, date) for x in f))

# --- TIR: a la par rinde el cupon -------------------------------------------------------
# Tolerancia de 0,01 pp: el tiempo se mide en dias / 365 y 2028 es bisiesto,
# asi que cinco anios son 1.827 dias y no 5 x 365.
t, c, corr = K.flujos(7.0, 1, date(2031, 3, 15), hoy)
check("bullet anual a la par, dia de cupon: TIR = cupon", abs(K.tir(100.0, t, c) - 7.0) < 0.01,
      f"{K.tir(100.0, t, c)}")
check("dia de cupon: corrido = 0", abs(corr) < 1e-12)
t, c, _ = K.flujos(8.0, 2, date(2031, 3, 15), hoy)
efectiva = ((1 + 0.04) ** 2 - 1) * 100
check("bullet semestral a la par: TIR efectiva anual", abs(K.tir(100.0, t, c) - efectiva) < 0.01,
      f"{K.tir(100.0, t, c)} contra {efectiva}")
check("NEG: mas precio, menos TIR", K.tir(105.0, t, c) < K.tir(100.0, t, c) < K.tir(95.0, t, c))

# Cupon corrido a mitad de periodo (cupon anual de 6 entre dos fechas de pago).
t, c, corr = K.flujos(6.0, 1, date(2031, 3, 15), date(2026, 9, 14))
check("corrido a mitad del periodo: medio cupon", abs(corr - 3.0) < 0.02, f"{corr}")

# Duration de un cero cupon.
t0, c0 = np.array([4.0]), np.array([100.0])
r = K.tir(100 / 1.06 ** 4, t0, c0)
check("cero cupon: TIR del precio descontado", abs(r - 6.0) < 1e-6, f"{r}")
check("cero cupon: duration modificada = t / (1 + r)",
      abs(K.duration_modificada(r, t0, c0) - 4 / 1.06) < 1e-9)

# --- Precio de mercado ------------------------------------------------------------------
p = pd.DataFrame({"compra": [99.0, 0.0, 0.0], "venta": [101.0, 102.0, 0.0], "ultimo": [98.0, 101.5, 0.0]})
pm = K.precio_de_mercado(p)
check("precio: punto medio con dos puntas", pm.iloc[0] == 100.0)
check("precio: con una punta, el ultimo", pm.iloc[1] == 101.5)
check("NEG precio: sin puntas ni ultimo, no hay precio", pd.isna(pm.iloc[2]))

# --- Vara por plazo ---------------------------------------------------------------------------
cv = pd.DataFrame({"plazo_anios": [0.3, 1.0, 4.2, 4.9, 5.4, 5.8, 9.0],
                   "tir_pct": [-3.0, 4.0, 6.0, 6.2, 6.4, 6.9, 7.5]})
v = K.tir_al_plazo(cv, 5)
check("vara a 5 anios: mediana de la ventana 4 a 6", v["mediana"] == 6.3 and v["n"] == 4, f"{v}")
check("vara: piso <= mediana <= techo", v["p25"] <= v["mediana"] <= v["p75"])
try:
    K.tir_al_plazo(cv, 8)
    check("NEG: con menos de MIN_ON en la ventana, no hay vara", False)
except ValueError:
    check("NEG: con menos de MIN_ON en la ventana, no hay vara", True)
try:
    K.tir_al_plazo(cv[cv["plazo_anios"] < 1.2], 0.6)
    check("NEG: las de menos de medio anio no cuentan", False)
except ValueError:
    check("NEG: las de menos de medio anio no cuentan", True)

# --- Con los precios guardados --------------------------------------------------------------
import os
if os.path.exists(K.PRECIOS):
    import supuestos as S
    real = K.curva()
    check("datos: todas las TIR finitas", np.isfinite(real["tir_pct"]).all())
    check("datos: la vara de supuestos.py sale de la curva",
          S.RETORNO_MIN_PCT == K.tir_al_plazo(real, S.HORIZONTE_ANIOS)["mediana"])
    # Contra la TIR de Criteria (otra fecha y otro precio): una diferencia
    # grande delata un cupon o un vencimiento mal transcripto.
    term = pd.read_csv(K.TERMINOS).set_index("especie")
    largo = real[real["plazo_anios"] > 1.5].set_index("especie")
    dif = (largo["tir_pct"] - term.loc[largo.index, "tir_criteria_pct"]).abs()
    check("datos: ninguna ON de mas de 1,5 anios se aleja 2 pp de la TIR de Criteria", (dif < 2).all(),
          dif[dif >= 2].round(2).to_dict())
    check("datos: la curva sube con el plazo (5 anios > 2 anios)",
          K.tir_al_plazo(real, 5)["mediana"] > K.tir_al_plazo(real, 2)["mediana"])
else:
    print("(sin precios guardados: se saltean los tests con datos)")

print(f"Tests corridos : {corridos}")
print(f"Fallos         : {len(fallos)}")
if fallos:
    print()
    for f in fallos:
        print(f"  FALLO: {f}")
    sys.exit(1)
print("OK")
sys.exit(0)
