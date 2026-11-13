#!/usr/bin/env python
"""
curva_on.py — La vara de la decision P1: la TIR de las ON corporativas en
dolares de primera linea, por plazo, con precios de mercado.

POR QUE UNA CURVA Y NO UN BONO
------------------------------
El inmueble se evalua a HORIZONTE_ANIOS (supuestos.py). La alternativa de
renta fija tiene que ser del mismo plazo: un bono a 11 anios paga mas que uno
a 5 por el plazo, no por ser mejor alternativa. Con una curva, la vara se lee
en el plazo del inversor y se puede leer en cualquier otro (1, 2, 3, 5 o 7
anios) si el inversor declara otro horizonte.

DE DONDE SALE CADA DATO
-----------------------
  - Terminos de cada ON (vencimiento, cupon, frecuencia, amortizacion):
    data/external/on_terminos.csv, transcriptos de Criteria, "Reporte de
    Obligaciones Negociables 2T2026" (tablas 6a y 6b, fichas por emisor),
    con precios al 02-07-2026. Solo ON BULLET en USD a tasa fija de emisores
    AAA(arg) o AA+(arg): con amortizacion parcial el plazo no es el
    vencimiento y la TIR necesita el cronograma completo.
  - Precios: API publica de data912.com (endpoint /live/arg_corp, precios
    de BYMA en dolares MEP, especie terminada en D). La consulta se guarda
    con su fecha en data/external/on_precios.csv para que la corrida sea
    reproducible sin red.

LA CONVENCION DE PRECIO
-----------------------
La API no dice si el precio incluye el cupon corrido, y las fuentes que
explican el mercado local se contradicen. Se decidio con los datos: si la
convencion supuesta es la equivocada, la diferencia contra la TIR de
referencia de Criteria crece con el cupon corrido de cada ON. Medido en
puntos de precio, la pendiente fue 0,81 suponiendo precio sucio (1 si fuera
del todo equivocada) y -0,28 suponiendo precio limpio (0 si fuera la
correcta). Se toma el precio como LIMPIO y el reporte informa la vara con la
otra convencion como sensibilidad.

LA TIR
------
Efectiva anual, la misma convencion que la TIR del inmueble (costos.tir):
la tasa r que iguala el precio sucio con los flujos descontados a (1+r)^t,
t en anios desde la fecha de la consulta. Los cupones se fechan hacia atras
desde el vencimiento con la frecuencia del bono.

Uso:
    py src/curva_on.py                 # curva con los precios guardados
    py src/curva_on.py --actualizar    # consulta la API y guarda los precios

Salidas:
    data/external/on_precios.csv        (solo con --actualizar)
    data/processed/curva_on.csv         TIR, plazo y duration de cada ON
    data/processed/reporte_curva_on.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date

import numpy as np
import pandas as pd

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TERMINOS = os.path.join(RAIZ, "data", "external", "on_terminos.csv")
PRECIOS = os.path.join(RAIZ, "data", "external", "on_precios.csv")
SALIDA = os.path.join(RAIZ, "data", "processed", "curva_on.csv")
REPORTE = os.path.join(RAIZ, "data", "processed", "reporte_curva_on.txt")
API = "https://data912.com/live/arg_corp"

# Por debajo de medio anio la TIR la mueven centavos de precio (duration casi
# nula) y la ON es un instrumento de liquidez, no una alternativa de inversion.
PLAZO_MIN_ANIOS = 0.5
# Ventana alrededor de cada plazo: la vara a h anios es la mediana de las ON
# que vencen entre h - VENTANA y h + VENTANA. Hacen falta al menos MIN_ON.
VENTANA_ANIOS = 1.0
MIN_ON = 3


# ==========================================================================
# FLUJOS Y TIR DE UNA ON BULLET
# ==========================================================================

def _restar_meses(d: date, meses: int) -> date:
    y, m = d.year, d.month - meses
    while m <= 0:
        m += 12
        y -= 1
    for dia in (d.day, 30, 29, 28):
        try:
            return date(y, m, dia)
        except ValueError:
            continue
    raise ValueError(d)


def cronograma(vencimiento: date, pagos_por_anio: int, hoy: date) -> tuple[list[date], date]:
    """Fechas de pago futuras (hasta el vencimiento) y la del ultimo cupon ya pagado."""
    paso = 12 // pagos_por_anio
    fechas, k = [], 0
    d = vencimiento
    while d > hoy:
        fechas.append(d)
        k += 1
        d = _restar_meses(vencimiento, paso * k)
    return sorted(fechas), d


def flujos(cupon_pct: float, pagos_por_anio: int, vencimiento: date, hoy: date):
    """Tiempos en anios y flujos por 100 de valor nominal, y el cupon corrido."""
    fechas, previo = cronograma(vencimiento, pagos_por_anio, hoy)
    t = np.array([(f - hoy).days / 365.0 for f in fechas])
    c = np.full(len(fechas), cupon_pct / pagos_por_anio)
    c[-1] += 100.0
    corrido = cupon_pct / pagos_por_anio * (hoy - previo).days / (fechas[0] - previo).days
    return t, c, corrido


def tir(precio_sucio: float, t: np.ndarray, c: np.ndarray) -> float:
    """TIR efectiva anual en %, por biseccion: el valor presente cae con la tasa."""
    lo, hi = -0.9, 2.0
    for _ in range(200):
        r = (lo + hi) / 2
        if (c / (1 + r) ** t).sum() > precio_sucio:
            lo = r
        else:
            hi = r
    return (lo + hi) / 2 * 100


def duration_modificada(r_pct: float, t: np.ndarray, c: np.ndarray) -> float:
    r = r_pct / 100
    vp = c / (1 + r) ** t
    return float((t * vp).sum() / vp.sum() / (1 + r))


# ==========================================================================
# PRECIOS
# ==========================================================================

def consultar_api(especies: list[str]) -> pd.DataFrame:
    """Precio en dolares MEP de cada especie (sufijo D) en la API de data912."""
    req = urllib.request.Request(API, headers={"User-Agent": "analisis-inmobiliario-caba"})
    with urllib.request.urlopen(req, timeout=30) as r:
        datos = {x["symbol"]: x for x in json.load(r)}
    filas = []
    for e in especies:
        x = datos.get(e + "D")
        if x is None:
            continue
        filas.append({"especie": e, "simbolo": e + "D", "compra": x["px_bid"], "venta": x["px_ask"],
                      "ultimo": x["c"], "operaciones": x["q_op"]})
    out = pd.DataFrame(filas)
    out.insert(0, "fecha", date.today().isoformat())
    return out


def precio_de_mercado(p: pd.DataFrame) -> pd.Series:
    """Punto medio entre compra y venta si hay puntas de los dos lados; si no, el ultimo."""
    dos_puntas = (p["compra"] > 0) & (p["venta"] > 0)
    return ((p["compra"] + p["venta"]) / 2).where(dos_puntas, p["ultimo"].where(p["ultimo"] > 0))


# ==========================================================================
# CURVA
# ==========================================================================

def curva(precio_limpio: bool = True, terminos: str = TERMINOS, precios: str = PRECIOS) -> pd.DataFrame:
    """TIR, plazo y duration de cada ON con precio, a la fecha de la consulta guardada."""
    term = pd.read_csv(terminos)
    pr = pd.read_csv(precios)
    df = term.merge(pr, on="especie", how="inner")
    df["precio"] = precio_de_mercado(df)
    df = df.dropna(subset=["precio"])
    filas = []
    for _, r in df.iterrows():
        hoy = date.fromisoformat(r["fecha"])
        venc = date.fromisoformat(r["vencimiento"])
        t, c, corrido = flujos(r["cupon_pct"], int(r["pagos_por_anio"]), venc, hoy)
        sucio = r["precio"] + (corrido if precio_limpio else 0.0)
        y = tir(sucio, t, c)
        filas.append({"especie": r["especie"], "emisor": r["emisor"], "ley": r["ley"], "fecha": r["fecha"],
                      "vencimiento": r["vencimiento"], "plazo_anios": round((venc - hoy).days / 365.0, 2),
                      "cupon_pct": r["cupon_pct"], "precio": round(r["precio"], 2), "corrido": round(corrido, 2),
                      "tir_pct": round(y, 2), "duration_mod": round(duration_modificada(y, t, c), 2),
                      "operaciones": r["operaciones"]})
    return pd.DataFrame(filas).sort_values("plazo_anios").reset_index(drop=True)


def en_ventana(cv: pd.DataFrame, plazo: float) -> pd.DataFrame:
    sel = cv[(cv["plazo_anios"] >= PLAZO_MIN_ANIOS)
             & cv["plazo_anios"].between(plazo - VENTANA_ANIOS, plazo + VENTANA_ANIOS)]
    if len(sel) < MIN_ON:
        raise ValueError(f"menos de {MIN_ON} ON con precio que venzan a {plazo} +- {VENTANA_ANIOS} anios")
    return sel


def tir_al_plazo(cv: pd.DataFrame, plazo: float) -> dict:
    """La vara a `plazo` anios: mediana de la ventana, con su p25 y p75 como banda."""
    sel = en_ventana(cv, plazo)["tir_pct"]
    return {"plazo": plazo, "n": int(len(sel)), "mediana": round(float(sel.median()), 2),
            "p25": round(float(sel.quantile(0.25)), 2), "p75": round(float(sel.quantile(0.75)), 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--actualizar", action="store_true", help="consultar la API y guardar los precios")
    args = ap.parse_args()
    if args.actualizar:
        especies = pd.read_csv(TERMINOS)["especie"].tolist()
        consultar_api(especies).to_csv(PRECIOS, index=False)
    if not os.path.exists(PRECIOS):
        print(f"No existe {PRECIOS}. Correr py src/curva_on.py --actualizar")
        return 1

    cv = curva()
    alt = curva(precio_limpio=False).set_index("especie")["tir_pct"]
    cv["tir_si_precio_sucio_pct"] = cv["especie"].map(alt)
    cv.to_csv(SALIDA, index=False)

    lineas = ["CURVA DE ON CORPORATIVAS EN USD (bullet, tasa fija)", "",
              f"Precios: {API}, consulta del {cv['fecha'].iloc[0]} (punto medio compra-venta)",
              f"Terminos: data/external/on_terminos.csv (Criteria, Reporte de ON 2T2026)",
              f"ON con precio: {len(cv)} de {len(pd.read_csv(TERMINOS))}", "",
              cv[["especie", "emisor", "ley", "vencimiento", "plazo_anios", "precio", "tir_pct",
                  "duration_mod", "operaciones"]].to_string(index=False), "",
              f"TIR por plazo: mediana de las ON que vencen a +- {VENTANA_ANIOS:g} anio "
              f"(sin las de menos de {PLAZO_MIN_ANIOS:g} anio)"]
    cv_alt = cv.assign(tir_pct=cv["tir_si_precio_sucio_pct"])
    for h in (1, 2, 3, 5, 7):
        try:
            v, a = tir_al_plazo(cv, h), tir_al_plazo(cv_alt, h)
        except ValueError as e:
            lineas.append(f"    {h} anios: {e}")
            continue
        lineas.append(f"    {h} anios: {v['mediana']:.2f}%  (p25 {v['p25']:.2f}%, p75 {v['p75']:.2f}%, "
                      f"{v['n']} ON)   si el precio fuera sucio: {a['mediana']:.2f}%")
    texto = "\n".join(lineas)
    print(texto)
    with open(REPORTE, "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
