#!/usr/bin/env python
"""
decision.py — La funcion de decision prescriptiva: P1, P2 y P3, implementadas
y evaluadas.

LAS TRES DECISIONES
---------------------------------------------------------------
  P1  comprar o no: se recomienda la propiedad solo si su rentabilidad neta
      calculada sobre el EXTREMO INFERIOR de su banda supera la TIR de las ON
      corporativas en USD al mismo plazo (curva_on.py), mas un margen por
      liquidez
  P2  que propiedad: A sobre B solo si sus bandas NO se superponen (la neta
      pesimista de A supera la optimista de B)
  P3  tradicional o temporal: neta contra neta, por la ocupacion de
      equilibrio de la celda barrio x dormitorios

EL EXTREMO INFERIOR, CON LOS MISMOS DESCUENTOS QUE EL KPI 2
-----------------------------------------------------------
La banda del KPI 4 es la del alquiler (percentiles 10 y 90). La neta de cada
extremo descuenta la misma vacancia y los mismos gastos que el KPI 2, con el
ABL de la propiedad en pesos: sobre un alquiler mas bajo, el ABL pesa mas.

EL SOPORTE DEL MODELO
---------------------
Solo se recomiendan propiedades cuya celda tipo x tramo de superficie tiene
al menos supuestos.MIN_ALQ_SOPORTE alquileres observados. Fuera de ese
soporte el alquiler estimado es extrapolacion, y sin el filtro las dos
primeras decisiones recomiendan justo las casas de 6 a 10 ambientes donde el
modelo menos sabe.

EL PRECIO TIENE QUE SER EL TOTAL
--------------------------------
Quedan afuera las ventas con financiacion del vendedor o en pozo
(variables.py): el precio publicado suele ser solo la parte al contado, y la
unidad en pozo no se alquila hasta la entrega. Ademas, las listas finales se
leyeron a mano (titulo y descripcion); lo que no corresponde se excluye o se
alerta en data/reference/revision_listas.csv, con su motivo.

EVALUAR, NO SOLO IMPLEMENTAR
----------------------------
  - cuantas propiedades pasan P1, con y sin costos de entrada
  - en que proporcion de los pares las bandas se superponen, y cuantas
    propiedades no estan dominadas por ninguna (la frontera de P2)
  - en cuantas celdas gana el temporal segun la ocupacion que se crea
  - como cambia todo eso con la vacancia, los gastos, el ABL, los costos de
    entrada, la banda de retorno y el margen por liquidez

Uso:
    py src/decision.py        # despues de kpis.py y temporal.py

Entradas:
    data/processed/dataset_analitico.csv
    data/processed/temporal_vs_tradicional.csv
    data/external/estadistica_ciudad_tiempo_publicacion.csv
    data/processed/modelo_alquiler.joblib     factores de suba por refaccion
    data/reference/revision_listas.csv        revision a mano de las listas
Salidas:
    data/processed/dataset_analitico.csv     + las columnas de COLUMNAS_DECISION
    data/processed/decision_sensibilidad.csv  P1 y P2 en cada escenario
    data/processed/decision_p3.csv            P3 por ocupacion y gestion
    data/processed/reporte_decision.txt
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

import costos as C
import supuestos as S
from modelo_alquiler import Reporte, factores_suba_refaccion


ANALITICO = "data/processed/dataset_analitico.csv"
TEMPORAL = "data/processed/temporal_vs_tradicional.csv"
LIQUIDEZ = "data/external/estadistica_ciudad_tiempo_publicacion.csv"
MODELO = "data/processed/modelo_alquiler.joblib"
REVISION = "data/reference/revision_listas.csv"
SALIDA_SENS = "data/processed/decision_sensibilidad.csv"
SALIDA_P3 = "data/processed/decision_p3.csv"
REPORTE = "data/processed/reporte_decision.txt"

# Columnas que este script agrega al dataset analitico. Si ya estan (una
# corrida anterior), se reemplazan: correrlo dos veces da el mismo archivo.
COLUMNAS_DECISION = [
    "en_presupuesto", "n_alq_celda_tipo", "en_soporte_modelo", "precio_es_total",
    "excluida_revision", "alerta_revision", "universo_decision",
    "neta_min_pct", "neta_max_pct", "tir_5a_min_pct",
    "p1_comprar", "p1_comprar_con_entrada", "p2_no_dominada",
    "m2_relativo_celda", "dias_publicacion_ambientes",
    "p3_ocupacion_equilibrio_pct", "p3_ocupacion_airbnb_pct",
]

BASE = {"vacancia": S.VACANCIA_PCT, "gastos_sin_abl": S.GASTOS_SIN_ABL_PCT, "abl": "segmentado",
        "entrada": "base", "refaccion": "base", "suba": S.SUBA_REFACCION, "horizonte": S.HORIZONTE_ANIOS,
        "umbral": S.RETORNO_MIN_PCT, "margen": S.MARGEN_LIQUIDEZ_PCT}


# ==========================================================================
# NETA EN LOS EXTREMOS DE LA BANDA
# ==========================================================================

def neta(alquiler, venta, abl_ars, vacancia: float, gastos_sin_abl: float) -> pd.Series:
    """
    Neta del KPI 2 para un alquiler dado: bruta x (1 - vacancia) x (1 - gastos),
    con gastos = gastos sin ABL + ABL en pesos sobre ese alquiler. Con
    abl_ars=None, el ABL plano de supuestos.py (un % fijo del alquiler).
    """
    bruta = alquiler * 12 / venta * 100
    if abl_ars is None:
        gastos = gastos_sin_abl + S.ABL_PCT
    else:
        gastos = gastos_sin_abl + abl_ars / (alquiler * S.TC_ARS_USD) * 100
    return bruta * (1 - vacancia / 100) * (1 - gastos / 100)


def abl_segun(v: pd.DataFrame, abl: str, abl_tope: pd.Series):
    """ABL en pesos por mes de cada venta segun la definicion; None = plano."""
    return {"plano": None, "segmentado": v["abl_ars_mes"], "segmentado_tope": abl_tope.loc[v.index]}[abl]


def bandas(v: pd.DataFrame, vacancia: float, gastos_sin_abl: float, abl_ars) -> pd.DataFrame:
    """Neta pesimista (p10), central y optimista (p90) de cada venta."""
    return pd.DataFrame({
        "neta_min": neta(v["alquiler_p10_usd_mes"], v["venta_usd"], abl_ars, vacancia, gastos_sin_abl),
        "neta": neta(v["alquiler_est_usd_mes"], v["venta_usd"], abl_ars, vacancia, gastos_sin_abl),
        "neta_max": neta(v["alquiler_p90_usd_mes"], v["venta_usd"], abl_ars, vacancia, gastos_sin_abl),
    }, index=v.index)


def tir_pesimista(v: pd.DataFrame, vacancia: float, gastos_sin_abl: float, abl_ars, entrada: str,
                  factores: dict, refaccion: str = "base", suba: str = S.SUBA_REFACCION,
                  horizonte: int = S.HORIZONTE_ANIOS) -> pd.Series:
    """
    TIR a `horizonte` anios con el alquiler del extremo inferior, los costos
    de entrada y la refaccion. Las unidades a reciclar cobran el p10 por el
    factor de suba del escenario `suba` (`factores`, de
    modelo_alquiler.factores_suba_refaccion) y pagan la obra del escenario
    `refaccion`.

    Los costos de entrada y la refaccion son parametros SEPARADOS: un
    escenario sin costos de entrada no puede cobrar el alquiler refaccionado
    sin pagar la obra.
    """
    sube = np.where(v["a_reciclar"].fillna(0) == 1, factores[suba], 1.0)
    n = neta(v["alquiler_p10_usd_mes"] * sube, v["venta_usd"], abl_ars, vacancia, gastos_sin_abl)
    inicial = (C.costos_entrada_pct(v["venta_usd"], entrada)
               + C.refaccion_usd(v, refaccion) / v["venta_usd"] * 100)
    return pd.Series(C.tir(n, inicial, anios=horizonte), index=v.index)


# ==========================================================================
# P2: DOMINANCIA DE BANDAS
# ==========================================================================

def no_dominadas(lo, hi) -> np.ndarray:
    """
    Propiedades que ninguna otra supera con claridad. B esta dominada si
    existe A con lo_A > hi_B; entonces B no esta dominada si y solo si su hi
    alcanza al mayor lo de todas. Dentro de la frontera ninguna domina a
    otra: la eleccion no la decide el KPI.
    """
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    return hi >= lo.max()


def pares_distinguibles(lo, hi) -> float:
    """
    Proporcion de los pares sin orden cuyas bandas no se superponen. Para
    cada A se cuentan las B con hi_B < lo_A; cada par distinguible se cuenta
    una sola vez, porque solo una de las dos puede quedar arriba.
    """
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    n = len(lo)
    if n < 2:
        return np.nan
    return float(np.searchsorted(np.sort(hi), lo, side="left").sum() / (n * (n - 1) / 2))


def pares_distinguibles_por_grupo(lo: pd.Series, hi: pd.Series, grupo: pd.Series) -> float:
    """Lo mismo, contando solo los pares dentro del mismo grupo."""
    dist = total = 0.0
    for _, idx in grupo.groupby(grupo).groups.items():
        n = len(idx)
        if n < 2:
            continue
        dist += np.searchsorted(np.sort(hi.loc[idx].values), lo.loc[idx].values, side="left").sum()
        total += n * (n - 1) / 2
    return dist / total if total else np.nan


# ==========================================================================
# P3: OCUPACION DE EQUILIBRIO
# ==========================================================================

def margen_temporal(autogestion: bool) -> float:
    """Lo que queda de cada dolar de ingreso por noches (igual que temporal.py)."""
    if autogestion:
        return (1 - S.COMISION_PLATAFORMA_PCT / 100) - S.MANTENIMIENTO_TEMPORAL_PCT / 100
    return ((1 - S.COMISION_PLATAFORMA_PCT / 100) * (1 - S.GESTION_TEMPORAL_PCT / 100)
            - S.MANTENIMIENTO_TEMPORAL_PCT / 100)


def ocupacion_equilibrio(t: pd.DataFrame, vacancia: float, autogestion: bool = False) -> pd.Series:
    """
    Ocupacion con la que el temporal empata al tradicional en cada celda:
    o = (neta tradicional + fijos) / (ingreso con 100% de ocupacion x margen).
    Con la vacancia de supuestos.py reproduce la columna de temporal.py.
    """
    trad = t["alquiler_est_mediano_usd"] * 12 * (1 - vacancia / 100) * (1 - t["gastos_mediana_pct"] / 100)
    return (trad + t["fijos_usd"]) / (t["adr_mediana_usd"] * 365 * margen_temporal(autogestion)) * 100


# ==========================================================================
# ESCENARIOS
# ==========================================================================

def leer_revision(ruta: str = REVISION) -> pd.DataFrame:
    """La revision a mano de las listas: id_aviso, accion (excluir o alertar) y motivo."""
    if not os.path.exists(ruta):
        return pd.DataFrame(columns=["id_aviso", "accion", "motivo"])
    r = pd.read_csv(ruta, encoding="utf-8-sig")
    malas = set(r["accion"]) - {"excluir", "alertar"}
    if malas:
        raise ValueError(f"{ruta}: acciones desconocidas {malas}")
    return r


def universo(df: pd.DataFrame, revision: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Ventas con estimacion confiable, dentro del presupuesto, con su soporte
    (cuantos alquileres observados hay en su celda tipo x tramo de superficie),
    con un precio publicado que es el total (sin financiacion ni pozo) y que
    la revision a mano no excluyo.
    """
    if revision is None:
        revision = leer_revision()
    alq = df[df["operacion"] == "alquiler"]
    n_celda = alq.groupby(["tipo_familia", "superficie_rango"]).size()
    v = df[(df["operacion"] == "venta") & (df["estimacion_confiable"] == 1)
           & df["alquiler_p10_usd_mes"].notna()].copy()
    v["n_alq_celda_tipo"] = (n_celda.reindex(pd.MultiIndex.from_frame(v[["tipo_familia", "superficie_rango"]]))
                             .fillna(0).astype(int).values)
    v["en_presupuesto"] = v["venta_usd"].between(*S.PRESUPUESTO_USD)
    v["en_soporte_modelo"] = v["n_alq_celda_tipo"] >= S.MIN_ALQ_SOPORTE
    v["precio_es_total"] = (v["financiacion"].fillna(0) != 1) & (v["en_pozo"].fillna(0) != 1)
    excl = revision.loc[revision["accion"] == "excluir"].set_index("id_aviso")["motivo"]
    alerta = revision.loc[revision["accion"] == "alertar"].set_index("id_aviso")["motivo"]
    v["excluida_revision"] = v["id_aviso"].isin(excl.index)
    texto = v["id_aviso"].map(pd.concat([excl, alerta]))
    regex = (v["uso_no_residencial"].fillna(0) == 1) & texto.isna()
    texto = texto.where(~regex, "El aviso menciona oficina o uso mixto (RegEx, sin revisar a mano).")
    # La superficie total suma terrazas y patios, que pagan poco alquiler: si
    # la cubierta es una parte chica, el alquiler estimado puede estar alto.
    cub = v["sup_cubierta_m2"] / v["sup_total_m2"]
    poca = (cub < S.MIN_CUBIERTA_SOBRE_TOTAL) & texto.isna()
    v["alerta_revision"] = texto.where(~poca, "Solo " + (cub * 100).round(0).astype("Int64").astype(str)
                                       + "% de la superficie es cubierta: el alquiler estimado sobre la total puede estar alto.")
    v["universo_decision"] = (v["en_presupuesto"] & v["en_soporte_modelo"] & v["precio_es_total"]
                              & ~v["excluida_revision"])
    return v


def escenario(u: pd.DataFrame, abl_tope: pd.Series, factores: dict, vacancia: float, gastos_sin_abl: float,
              abl: str, entrada: str, refaccion: str, suba: str, horizonte: int, umbral: float,
              margen: float) -> dict:
    """P1 y P2 sobre el universo `u` con un juego de supuestos."""
    ars = abl_segun(u, abl, abl_tope)
    b = bandas(u, vacancia, gastos_sin_abl, ars)
    t = tir_pesimista(u, vacancia, gastos_sin_abl, ars, entrada, factores, refaccion, suba, horizonte)
    p1 = b["neta_min"] > umbral + margen
    p1e = t > umbral + margen
    front = no_dominadas(b["neta_min"], b["neta_max"])
    return {"p1": set(u.index[p1]), "p1_entrada": set(u.index[p1e]), "frontera": set(u.index[front]),
            "n_p1": int(p1.sum()), "n_p1_entrada": int(p1e.sum()), "n_frontera": int(front.sum()),
            "pares_distinguibles": pares_distinguibles(b["neta_min"], b["neta_max"]),
            "neta_min_mediana": float(b["neta_min"].median())}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a | b) else 1.0


def sensibilidad(u: pd.DataFrame, abl_tope: pd.Series, factores: dict) -> pd.DataFrame:
    """
    Un parametro por vez, los demas en el caso base, y dos extremos. Para
    cada escenario: cuantas pasan P1 (con y sin costos de entrada), el tamanio
    de la frontera de P2, los pares distinguibles, y cuanto se parecen las
    recomendaciones a las del caso base (Jaccard: 1 = las mismas propiedades).
    """
    variaciones = [("base", {})]
    variaciones += [("vacancia", {"vacancia": x}) for x in S.SENSIBILIDAD_VACANCIA]
    variaciones += [("gastos sin ABL", {"gastos_sin_abl": round(S.GASTOS_SIN_ABL_PCT + d, 2)})
                    for d in S.SENSIBILIDAD_GASTOS_SIN_ABL_DELTA]
    variaciones += [("ABL", {"abl": x}) for x in S.SENSIBILIDAD_ABL]
    variaciones += [("costos de entrada", {"entrada": x}) for x in S.SENSIBILIDAD_ENTRADA]
    variaciones += [("refaccion", {"refaccion": x}) for x in S.SENSIBILIDAD_REFACCION]
    variaciones += [("suba por refaccion", {"suba": x}) for x in S.SENSIBILIDAD_SUBA_REFACCION]
    variaciones += [("banda de retorno", {"umbral": x}) for x in S.RETORNO_MINIMO_BANDA]
    # Otro horizonte cambia las dos puntas: la TIR del inmueble (los costos se
    # reparten en menos anios) y la vara (la ON de ese plazo).
    variaciones += [("horizonte", {"horizonte": h, "umbral": S.retorno_minimo(h)["mediana"]})
                    for h in S.SENSIBILIDAD_HORIZONTE]
    variaciones += [("margen por liquidez", {"margen": x}) for x in S.SENSIBILIDAD_MARGEN]
    variaciones += [
        ("extremo favorable", {"vacancia": min(S.SENSIBILIDAD_VACANCIA), "abl": "plano", "entrada": "sin",
                               "refaccion": "base", "suba": "modelo",
                               "gastos_sin_abl": round(S.GASTOS_SIN_ABL_PCT + min(S.SENSIBILIDAD_GASTOS_SIN_ABL_DELTA), 2),
                               "umbral": S.RETORNO_MIN_PISO_PCT, "margen": 0.0}),
        ("extremo desfavorable", {"vacancia": max(S.SENSIBILIDAD_VACANCIA), "abl": "segmentado_tope", "entrada": "alto",
                                  "refaccion": "alto", "suba": "sin",
                                  "gastos_sin_abl": round(S.GASTOS_SIN_ABL_PCT + max(S.SENSIBILIDAD_GASTOS_SIN_ABL_DELTA), 2),
                                  "umbral": S.RETORNO_MIN_TECHO_PCT, "margen": max(S.SENSIBILIDAD_MARGEN)}),
    ]
    base = escenario(u, abl_tope, factores, **BASE)
    filas = []
    for parametro, cambio in variaciones:
        p = {**BASE, **cambio}
        e = escenario(u, abl_tope, factores, **p)
        filas.append({"parametro": parametro, **p,
                      "n_p1": e["n_p1"], "n_p1_con_entrada": e["n_p1_entrada"],
                      "jaccard_p1_vs_base": round(jaccard(e["p1"], base["p1"]), 3),
                      "n_frontera_p2": e["n_frontera"],
                      "jaccard_frontera_vs_base": round(jaccard(e["frontera"], base["frontera"]), 3),
                      "pares_distinguibles_pct": round(e["pares_distinguibles"] * 100, 2),
                      "neta_min_mediana": round(e["neta_min_mediana"], 2)})
    return pd.DataFrame(filas)


def sensibilidad_p3(t: pd.DataFrame) -> pd.DataFrame:
    """Celdas donde gana el temporal, por ocupacion sostenible, gestion y vacancia."""
    filas = []
    for autogestion in (False, True):
        for vac in sorted({S.VACANCIA_PCT, *S.SENSIBILIDAD_VACANCIA}):
            eq = ocupacion_equilibrio(t, vac, autogestion)
            for oc in S.SENSIBILIDAD_OCUPACION + [S.OCUPACION_REF_PCT]:
                filas.append({"gestion": "autogestionado" if autogestion else "tercerizada",
                              "vacancia_tradicional_pct": vac, "ocupacion_sostenible_pct": oc,
                              "celdas": len(t), "gana_temporal": int((oc > eq).sum()),
                              "equilibrio_mediano_pct": round(float(eq.median()), 1)})
    return pd.DataFrame(filas)


def liquidez_por_ambientes(ruta: str = LIQUIDEZ) -> pd.Series:
    """
    Dias que un aviso pasa publicado, por cantidad de ambientes, en el ultimo
    trimestre de IDECBA. Es para toda la Ciudad: no distingue barrios.
    """
    t = pd.read_csv(ruta, encoding="utf-8-sig")
    t = t[t["trimestre"] == t["trimestre"].max()].set_index("ambientes")["dias"]
    return t


def dias_por_ambientes(ambientes: pd.Series, liq: pd.Series) -> pd.Series:
    clave = ambientes.clip(lower=1).map(lambda a: "5 ambientes y más" if a >= 5 else
                                        ("1 ambiente" if a == 1 else f"{int(a)} ambientes"))
    return clave.map(liq)


# ==========================================================================
# MAIN
# ==========================================================================

def main() -> int:
    for p in (ANALITICO, TEMPORAL, LIQUIDEZ, MODELO):
        if not os.path.exists(p):
            print(f"No existe {p}. Correr el pipeline hasta py src/temporal.py")
            return 1
    rep = Reporte()
    rep.titulo("FUNCION DE DECISION: P1, P2 Y P3")
    rep(f"Fecha: {datetime.now():%Y-%m-%d %H:%M}")

    df = pd.read_csv(ANALITICO, encoding="utf-8-sig", low_memory=False)
    df = df.drop(columns=[c for c in COLUMNAS_DECISION if c in df.columns])
    ventas = df[df["operacion"] == "venta"].dropna(subset=["venta_usd", "sup_total_m2", "barrio"])
    # ABL con la VFH en el tope legal, para la sensibilidad: el m2 de mercado
    # de cada celda sale de todas las ventas, como en kpis.py.
    abl_tope = C.abl_por_propiedad(ventas, S.VFH_TOPE_SOBRE_MERCADO)["abl_ars_mes"]

    factores = factores_suba_refaccion(joblib.load(MODELO)["pipeline"])
    revision = leer_revision()
    v = universo(df, revision)
    u = v[v["universo_decision"]]
    rep(f"Ventas con estimacion confiable: {len(v):,}. En el presupuesto (USD {S.PRESUPUESTO_USD[0]:,} a "
        f"{S.PRESUPUESTO_USD[1]:,}): {int(v['en_presupuesto'].sum()):,}")
    fuera = v[v["en_presupuesto"] & ~v["en_soporte_modelo"]]
    rep(f"    fuera del soporte del modelo (celda tipo x tramo con menos de {S.MIN_ALQ_SOPORTE} alquileres): "
        f"{len(fuera):,}, {fuera['tipo_familia'].value_counts().to_dict()}")
    cand = v[v["en_presupuesto"] & v["en_soporte_modelo"]]
    rep(f"    con financiacion del vendedor o en pozo (el precio publicado no es el total): "
        f"{int((~cand['precio_es_total']).sum()):,} (financiacion {int((cand['financiacion'] == 1).sum())}, "
        f"pozo {int((cand['en_pozo'] == 1).sum())})")
    rep(f"    excluidas por la revision a mano: {int(cand['excluida_revision'].sum())}; "
        f"con alerta: {int(cand['alerta_revision'].notna().sum())}")
    rep(f"    universo de la decision: {len(u):,}")

    # --- Caso base -----------------------------------------------------------
    b = bandas(v, BASE["vacancia"], BASE["gastos_sin_abl"], v["abl_ars_mes"])
    v["neta_min_pct"], v["neta_max_pct"] = b["neta_min"].round(2), b["neta_max"].round(2)
    v["tir_5a_min_pct"] = tir_pesimista(v, BASE["vacancia"], BASE["gastos_sin_abl"], v["abl_ars_mes"],
                                        BASE["entrada"], factores, BASE["refaccion"], BASE["suba"],
                                        BASE["horizonte"]).round(2)
    umbral = BASE["umbral"] + BASE["margen"]
    v["p1_comprar"] = v["universo_decision"] & (v["neta_min_pct"] > umbral)
    v["p1_comprar_con_entrada"] = v["universo_decision"] & (v["tir_5a_min_pct"] > umbral)
    front = pd.Series(False, index=v.index)
    front.loc[u.index] = no_dominadas(v.loc[u.index, "neta_min_pct"], v.loc[u.index, "neta_max_pct"])
    v["p2_no_dominada"] = front
    m2_celda = ventas.groupby(["barrio", "superficie_rango"])["venta_m2_usd"].median()
    v["m2_relativo_celda"] = (v["venta_m2_usd"].values
                              / m2_celda.reindex(pd.MultiIndex.from_frame(v[["barrio", "superficie_rango"]])).values).round(2)
    v["dias_publicacion_ambientes"] = dias_por_ambientes(v["ambientes"], liquidez_por_ambientes())

    uu = v.loc[u.index]
    rep.titulo("P1: COMPRAR O NO COMPRAR")
    rep(f"Criterio: neta del extremo inferior > TIR de las ON a {S.HORIZONTE_ANIOS} anios "
        f"({BASE['umbral']:.2f}%, curva del {S.CURVA_ON_FECHA}) + margen por liquidez ({BASE['margen']:.2f} pp)")
    rep(f"Suba del alquiler al refaccionar (supuesto '{BASE['suba']}'): "
        f"{(factores[BASE['suba']] - 1) * 100:+.1f}%; con el efecto completo del modelo seria "
        f"{(factores['modelo'] - 1) * 100:+.1f}%")
    rep(f"    pasan: {int(uu['p1_comprar'].sum())} de {len(uu):,} ({uu['p1_comprar'].mean():.1%})")
    rep(f"    con costos de entrada (TIR pesimista a {S.HORIZONTE_ANIOS} anios): "
        f"{int(uu['p1_comprar_con_entrada'].sum())}")
    rep(f"    sin el filtro de soporte habrian pasado: "
        f"{int((v['en_presupuesto'] & (v['neta_min_pct'] > umbral)).sum())}")
    rep(f"    neta pesimista mediana del universo: {uu['neta_min_pct'].median():.2f}%; central: "
        f"{uu['rent_neta_pct'].median():.2f}%")
    p1 = uu[uu["p1_comprar"]]
    if len(p1):
        rep(f"    las que pasan: m2 de venta = {p1['m2_relativo_celda'].median():.2f} del mediano de su celda "
            f"barrio x tramo (mediana); barrios {p1['barrio'].value_counts().to_dict()}")

    rep.titulo("P2: QUE PROPIEDAD")
    rep(f"Pares con bandas que no se superponen: {pares_distinguibles(uu['neta_min_pct'], uu['neta_max_pct']):.1%}")
    rep(f"    dentro del mismo tramo de superficie: "
        f"{pares_distinguibles_por_grupo(uu['neta_min_pct'], uu['neta_max_pct'], uu['superficie_rango']):.1%}")
    rep(f"    dentro del mismo barrio: "
        f"{pares_distinguibles_por_grupo(uu['neta_min_pct'], uu['neta_max_pct'], uu['barrio']):.1%}")
    rep(f"Frontera (ninguna otra la supera): {int(uu['p2_no_dominada'].sum())} propiedades")
    rep(f"    ancho mediano de la banda de neta: {(uu['neta_max_pct'] - uu['neta_min_pct']).median():.2f} pp")
    mejor = uu["rent_neta_pct"].idxmax()
    rep(f"    la de mayor neta central ({uu.loc[mejor, 'rent_neta_pct']:.2f}%) supera con claridad al "
        f"{(uu['neta_max_pct'] < uu.loc[mejor, 'neta_min_pct']).mean():.1%} del universo")

    rep.titulo("P3: TRADICIONAL O TEMPORAL")
    t = pd.read_csv(TEMPORAL, encoding="utf-8-sig")
    eq = ocupacion_equilibrio(t, S.VACANCIA_PCT)
    rep(f"Celdas barrio x dormitorios: {len(t)}. Ocupacion de equilibrio mediana: {eq.median():.1f}% "
        f"(autogestionado {ocupacion_equilibrio(t, S.VACANCIA_PCT, True).median():.1f}%)")
    rep(f"    gana el temporal con la ocupacion de Inside Airbnb: {int((t['ocupacion_mediana_pct'] > eq).sum())}; "
        f"con {S.OCUPACION_REF_PCT:.0f}%: {int((S.OCUPACION_REF_PCT > eq).sum())}")
    celda = v["barrio"] + "|" + pd.cut(v["dormitorios"], [-0.5, 1, 2, 99], labels=["0-1", "2", "3+"]).astype(str)
    t["clave"] = t["barrio"] + "|" + t["dormitorios_grupo"].astype(str)
    v["p3_ocupacion_equilibrio_pct"] = celda.map(t.set_index("clave")["ocupacion_equilibrio_pct"]).round(1)
    v["p3_ocupacion_airbnb_pct"] = celda.map(t.set_index("clave")["ocupacion_mediana_pct"]).round(1)

    # --- Sensibilidad ----------------------------------------------------------
    rep.titulo("SENSIBILIDAD")
    sens = sensibilidad(u, abl_tope, factores)
    p3 = sensibilidad_p3(t)
    cols = ["parametro", "vacancia", "gastos_sin_abl", "abl", "entrada", "refaccion", "suba", "horizonte",
            "umbral", "margen",
            "n_p1", "n_p1_con_entrada", "jaccard_p1_vs_base", "n_frontera_p2", "jaccard_frontera_vs_base",
            "pares_distinguibles_pct"]
    rep(sens[cols].to_string(index=False))
    rep("")
    rep("P3, gestion tercerizada y vacancia base: celdas donde gana el temporal por ocupacion sostenible")
    q = p3[(p3["gestion"] == "tercerizada") & (p3["vacancia_tradicional_pct"] == S.VACANCIA_PCT)]
    rep("    " + ", ".join(f"{o:.0f}%: {g}" for o, g in zip(q["ocupacion_sostenible_pct"], q["gana_temporal"])))

    # --- Salidas ---------------------------------------------------------------
    nuevas = v[COLUMNAS_DECISION]
    out = df.join(nuevas)
    for c in ["en_presupuesto", "en_soporte_modelo", "precio_es_total", "excluida_revision",
              "universo_decision", "p1_comprar", "p1_comprar_con_entrada", "p2_no_dominada"]:
        out[c] = out[c].astype("boolean")
    out["n_alq_celda_tipo"] = out["n_alq_celda_tipo"].astype("Int64")
    out.to_csv(ANALITICO, index=False, encoding="utf-8-sig")
    sens.to_csv(SALIDA_SENS, index=False, encoding="utf-8-sig")
    p3.to_csv(SALIDA_P3, index=False, encoding="utf-8-sig")
    rep("")
    rep(f"Archivos: {ANALITICO} ({len(out):,} x {out.shape[1]}), {SALIDA_SENS}, {SALIDA_P3}")
    rep.guardar(REPORTE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
