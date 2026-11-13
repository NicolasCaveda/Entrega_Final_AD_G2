#!/usr/bin/env python
"""
credito_y_verdes.py — Dos preguntas del planteo inicial que el analisis no
habia respondido: cuantos avisos son aptos para credito hipotecario, y si
estar cerca de una plaza o un parque cambia el precio del m2.

1. APTOS PARA CREDITO
---------------------
La variable apto_credito (variables.py) marca el aviso que DICE ser apto
para credito hipotecario, con el veto por negacion ("no apto credito"). No
decir nada no es lo mismo que no ser apto: la proporcion es un piso.

Para el inversor importa por la salida: una unidad apta se puede revender a
un comprador con hipoteca, un mercado mucho mas grande que el de quien paga
al contado. Se informa:
  - la proporcion en las ventas, en el universo de la decision y en las
    listas de P1
  - si el m2 de las aptas cotiza distinto que el de sus comparables: la
    diferencia de medianas DENTRO de cada celda barrio x tramo de superficie
    (como H3), con el Mann-Whitney estratificado de Van Elteren

2. PRIMA POR CERCANIA A ESPACIOS VERDES
---------------------------------------
El mismo metodo que H2 (accesibilidad.py): regresion de log(USD/m2) con
efectos fijos de barrio y los controles del inmueble, ahora con tramos de
distancia a la plaza y al parque mas cercanos (espacial.py). Se agrega la
distancia a la red de transporte como control, para no confundir la plaza
con la estacion de al lado. Los errores se agrupan por barrio (CR1, como en
el test formal de H2): dentro de un barrio los avisos comparten lo que no se
mide. Es una ASOCIACION entre avisos del mismo barrio, no un efecto causal:
la plaza puede estar en la parte mas linda del barrio por otras razones.

Uso:
    py src/credito_y_verdes.py       # despues de decision.py

Salidas:
    data/processed/credito_verdes.csv       una fila por estimacion
    data/processed/reporte_credito_verdes.txt
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

import eda
import supuestos as S
import validacion as V
from accesibilidad import efecto_pct, matriz_base
from fuentes_externas import Reporte

ANALITICO = "data/processed/dataset_analitico.csv"
SALIDA = "data/processed/credito_verdes.csv"
REPORTE = "data/processed/reporte_credito_verdes.txt"
ESTRATO = ["barrio", "superficie_rango"]


def _bool(df: pd.DataFrame, c: str) -> pd.Series:
    return df[c].fillna(False).astype(bool)


# ==========================================================================
# 1. CREDITO
# ==========================================================================

def credito(df: pd.DataFrame, rep: Reporte) -> list[dict]:
    rep.titulo("1. AVISOS APTOS PARA CREDITO HIPOTECARIO")
    v = df[(df["operacion"] == "venta") & df["venta_usd"].notna()]
    grupos = [
        ("ventas", v),
        ("ventas en el presupuesto", v[v["venta_usd"].between(*S.PRESUPUESTO_USD)]),
        ("universo de la decision", v[_bool(v, "universo_decision")]),
        ("P1: pasan sin costos de entrada", v[_bool(v, "p1_comprar")]),
        ("P1: pasan con costos de entrada", v[_bool(v, "p1_comprar_con_entrada")]),
    ]
    filas = []
    rep("Proporcion de avisos que declaran ser aptos para credito (un piso: no decirlo no es no serlo)")
    for nombre, g in grupos:
        p = g["apto_credito"].mean() * 100
        rep(f"    {nombre:<34} {int(g['apto_credito'].sum()):>6,} de {len(g):>6,}  {p:5.1f}%")
        filas.append({"bloque": "credito", "medida": f"proporcion apto credito: {nombre}", "n": len(g),
                      "valor": round(p, 1), "ic_inf": np.nan, "ic_sup": np.nan, "p_valor": np.nan})
    rep("")
    rep("Por tipo de propiedad (ventas):")
    for t, g in v.groupby("tipo_familia"):
        rep(f"    {t:<14} {g['apto_credito'].mean() * 100:5.1f}%  ({len(g):,} avisos)")

    # Precio del m2: aptas contra no aptas, dentro de la celda barrio x tramo.
    ok = v[v["venta_m2_usd"].notna()]
    t = eda.efecto_estratificado(ok, "apto_credito", "venta_m2_usd", ESTRATO, S.MIN_GRUPO_ESTRATO)
    rel = eda.mediana_ponderada(t["diferencia"] / t["mediana_0"], t["peso"]) * 100
    ve = V.van_elteren(ok["venta_m2_usd"], ok["apto_credito"], ok["barrio"] + "|" + ok["superficie_rango"].astype(str),
                       S.MIN_GRUPO_ESTRATO)
    rep("")
    rep(f"Precio del m2, aptas contra no aptas en la misma celda barrio x tramo ({len(t)} celdas):")
    rep(f"    diferencia mediana ponderada: {rel:+.1f}%   Van Elteren p bilateral = {ve['p_bilateral']:.2g}")
    filas.append({"bloque": "credito", "medida": "m2 apto contra no apto, misma celda (%)", "n": int(t["peso"].sum()),
                  "valor": round(rel, 1), "ic_inf": np.nan, "ic_sup": np.nan, "p_valor": ve["p_bilateral"]})
    return filas


# ==========================================================================
# 2. ESPACIOS VERDES
# ==========================================================================

def tramos(dist: pd.Series, bordes: list) -> pd.Series:
    b = bordes + [np.inf]
    etiquetas = [f"{x:,}-{y:,}" if np.isfinite(y) else f"{x:,}+" for x, y in zip(b[:-1], b[1:])]
    return pd.cut(dist, b, labels=etiquetas, right=False)


def prima_verde(v: pd.DataFrame, col: str, bordes: list, controles: bool) -> pd.DataFrame:
    """Efecto de cada tramo contra el MAS LEJANO, con IC 95% agrupado por barrio."""
    tr = tramos(v[col], bordes)
    D = pd.get_dummies(tr, dtype=float)
    ref = D.columns[-1]                     # el tramo lejano es la referencia
    X = np.hstack([matriz_base(v, controles), v[["dist_transporte_m"]].values / 1000,
                   D.drop(columns=ref).values])
    b, se = V.ols_agrupado(X, v["y"].values, v["barrio"].values)
    G = v["barrio"].nunique()
    z = stats.t.ppf(0.975, G - 1)
    k = D.shape[1] - 1
    filas = []
    for et, coef, e in zip(D.columns[:-1], b[-k:], se[-k:]):
        filas.append({"tramo_m": et, "n": int((tr == et).sum()), "efecto_pct": efecto_pct(coef),
                      "ic_inf": efecto_pct(coef - z * e), "ic_sup": efecto_pct(coef + z * e),
                      "p_valor": float(2 * stats.t.sf(abs(coef / e), G - 1))})
    filas.append({"tramo_m": ref, "n": int((tr == ref).sum()), "efecto_pct": 0.0,
                  "ic_inf": np.nan, "ic_sup": np.nan, "p_valor": np.nan})
    return pd.DataFrame(filas)


def verdes(df: pd.DataFrame, rep: Reporte) -> list[dict]:
    rep.titulo("2. PRIMA POR CERCANIA A ESPACIOS VERDES")
    v = df[(df["operacion"] == "venta") & df["venta_m2_usd"].notna() & df["dist_plaza_m"].notna()].copy()
    v["y"] = np.log(v["venta_m2_usd"])
    rep(f"Base: {len(v):,} ventas con precio del m2 y coordenadas. Plaza: desde {1_000:,} m2; parque: desde una")
    rep("hectarea; sin canteros centrales (espacial.py).")
    rep("Modelo: log(m2) = barrio + controles del inmueble + distancia a la red + tramos de distancia")
    rep("al verde. Efecto contra el tramo MAS LEJANO, IC 95% con errores agrupados por barrio.")
    filas = []
    for col, nombre, bordes in [("dist_plaza_m", "plaza", S.TRAMOS_PLAZA_M),
                                ("dist_parque_m", "parque", S.TRAMOS_PARQUE_M)]:
        for esp, sub, ctrl in [("barrio + controles", v, True),
                               ("barrio + controles, deptos", v[v["tipo_familia"] == "departamento"], True)]:
            p = prima_verde(sub, col, bordes, ctrl)
            rep("")
            rep(f"{nombre} ({esp}):")
            for _, f in p.iterrows():
                ic = "" if np.isnan(f["ic_inf"]) else f"  IC 95% [{f['ic_inf']:+.1f}%, {f['ic_sup']:+.1f}%]  p = {f['p_valor']:.2g}"
                rep(f"    {f['tramo_m']:>12} m  {int(f['n']):>6,} avisos  {f['efecto_pct']:+6.1f}%{ic}")
                if not np.isnan(f["ic_inf"]):
                    filas.append({"bloque": "verdes", "medida": f"{nombre}, {esp}, {f['tramo_m']} m contra el tramo lejano (%)",
                                  "n": int(f["n"]), "valor": round(f["efecto_pct"], 1), "ic_inf": round(f["ic_inf"], 1),
                                  "ic_sup": round(f["ic_sup"], 1), "p_valor": f["p_valor"]})
    return filas


def lectura(f: pd.DataFrame, rep: Reporte) -> None:
    """La lectura se arma con las cifras de arriba, para que no pueda contradecirlas."""
    rep.titulo("LECTURA")
    c = f[f["bloque"] == "credito"].set_index("medida")
    rep(f"- Declaran ser aptos para credito {c.loc['proporcion apto credito: ventas', 'valor']:.0f}% de las ventas y "
        f"{c.loc['proporcion apto credito: universo de la decision', 'valor']:.0f}% del universo de la decision.")
    m = c.loc["m2 apto contra no apto, misma celda (%)"]
    rep(f"- Contra sus comparables de la misma celda, el m2 de las aptas cotiza {m['valor']:+.1f}% "
        f"(Van Elteren, p bilateral = {m['p_valor']:.2g}).")
    rep("  Es una asociacion: la diferencia puede venir de lo que la celda no controla (antiguedad, estado).")
    for nombre in ("plaza", "parque"):
        for esp, deptos in (("todas", False), ("departamentos", True)):
            g = f[f["medida"].str.startswith(f"{nombre}, barrio + controles") & (f["medida"].str.contains("deptos") == deptos)]
            cerca = g.iloc[0]
            signif = "el intervalo no incluye el cero" if cerca["ic_inf"] > 0 or cerca["ic_sup"] < 0 else \
                "el intervalo incluye el cero: con estos datos no se distingue de cero, lo que no es lo mismo que no tener efecto"
            tramo = cerca["medida"].split(", ")[-1].split(" contra")[0]
            rep(f"- {nombre.capitalize()}, {esp}: a {tramo} el m2 cotiza {cerca['valor']:+.1f}% contra el tramo mas lejano, "
                f"IC 95% [{cerca['ic_inf']:+.1f}%, {cerca['ic_sup']:+.1f}%]; {signif}.")
    rep("  Son asociaciones entre avisos del mismo barrio, no efectos causales, y se prueban varios tramos sin")
    rep("  corregir por comparaciones multiples: un intervalo que apenas excluye el cero es evidencia debil.")


def main() -> int:
    if not os.path.exists(ANALITICO):
        print(f"No existe {ANALITICO}. Correr el pipeline hasta py src/decision.py")
        return 1
    rep = Reporte()
    rep.titulo("APTOS PARA CREDITO Y PRIMA POR ESPACIOS VERDES")
    rep(f"Fecha: {datetime.now():%Y-%m-%d %H:%M}")
    df = pd.read_csv(ANALITICO, encoding="utf-8-sig", low_memory=False)
    f = pd.DataFrame(credito(df, rep) + verdes(df, rep))
    lectura(f, rep)
    f.to_csv(SALIDA, index=False, encoding="utf-8-sig")
    rep("")
    rep(f"Archivo: {SALIDA} ({len(f)} filas)")
    with open(REPORTE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rep.lineas))
    print("\n".join(rep.lineas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
