#!/usr/bin/env python
"""
reporte.py — Emite informe/INFORME_HALLAZGOS.md con todas las cifras calculadas en vivo.

POR QUE UN SCRIPT Y NO UN DOCUMENTO ESCRITO A MANO
--------------------------------------------------
Un informe tipeado se desincroniza del dataset la primera vez que alguien
reejecuta el pipeline, y nadie se entera. Aca cada numero del texto sale de un
f-string alimentado por los datos: si cambia un supuesto o se corrige la
limpieza, el informe se regenera con los numeros nuevos. Las cifras narradas
coinciden con las calculadas por construccion. Hasta los titulos dependen del
dato, para que no puedan afirmar lo contrario de lo que muestra la tabla.

COMO SE ORDENA
--------------
Los hallazgos se ordenan por cuanto cambian la decision del inversor, y solo
quedan los que la cambian. Los tests se recalculan con
validacion.resumen_hipotesis, que usa los procedimientos y las semillas del
notebook 04.

Uso:
    py src/reporte.py      (al final del pipeline: despues de decision.py y sesgo.py)

Salida:
    informe/INFORME_HALLAZGOS.md
    README.md, el bloque de hallazgos entre las marcas <!-- hallazgos:inicio --> y fin
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

import costos as C
import decision as D
import eda
import modelo_alquiler as M
import sintesis as SI
import supuestos as S
import validacion as V


P = "data/processed"
E = "data/external"
SALIDA = "informe/INFORME_HALLAZGOS.md"
G = "../graficos"            # los graficos, vistos desde informe/
ESTRATO = ["barrio", "superficie_rango"]


# --------------------------------------------------------------------------
# Formato en castellano: coma decimal y punto de miles
# --------------------------------------------------------------------------

def num(x: float, d: int = 0) -> str:
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x: float, d: int = 1, signo: bool = False) -> str:
    return (f"{'+' if signo and x > 0 else ''}" + num(x, d)) + "%"


def pp(x: float, d: int = 2, signo: bool = True) -> str:
    return (f"{'+' if signo and x > 0 else ''}" + num(x, d)) + " pp"


def usd(x: float) -> str:
    return "USD " + num(x, 0)


def ic(par, d: int = 1, unidad: str = "") -> str:
    return f"[{num(par[0], d)}{unidad}, {num(par[1], d)}{unidad}]"


def pval(p: float) -> str:
    return "< 0,001" if p < 0.001 else num(p, 3)


def lista(items) -> str:
    """'4, 8 y 9' en vez de '4, 8, 9'."""
    items = [str(i) for i in items]
    if len(items) <= 1:
        return "".join(items) or "ninguna"
    return ", ".join(items[:-1]) + " y " + items[-1]


def trimestre(tr: str) -> str:
    """'2026-T2' -> '2do trimestre de 2026'."""
    anio, q = tr.split("-T")
    return f"{ {'1': '1er', '2': '2do', '3': '3er', '4': '4to'}[q] } trimestre de {anio}"


def fecha(iso: str) -> str:
    return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d-%m-%Y")


def grafico(n: int, nombre: str, alt: str) -> str:
    return f"![{alt}]({G}/{n:02d}_{nombre}.png)"


# --------------------------------------------------------------------------
# Calculos
# --------------------------------------------------------------------------

def leer(nombre: str, carpeta: str = P) -> pd.DataFrame:
    return pd.read_csv(os.path.join(carpeta, nombre), encoding="utf-8-sig", low_memory=False)


def calcular() -> dict:
    """Todos los numeros del informe, en un solo lugar."""
    df = leer("dataset_analitico.csv")
    for c in ["en_presupuesto", "en_soporte_modelo", "precio_es_total", "excluida_revision", "universo_decision",
              "p1_comprar", "p1_comprar_con_entrada", "p2_no_dominada"]:
        df[c] = df[c].fillna(False).astype(bool)
    ok = df[(df.operacion == "venta") & (df.estimacion_confiable == 1) & df.rent_bruta_pct.notna()]
    u = df[df.universo_decision]
    piso, techo = S.RETORNO_MINIMO_BANDA
    vara = S.RETORNO_MIN_PCT + S.MARGEN_LIQUIDEZ_PCT
    curva = {h: S.retorno_minimo(h)["mediana"] for h in (1, 2, 3, 5)}
    r = {"n_ok": len(ok), "n_u": len(u), "piso": piso, "techo": techo, "vara": vara, "curva": curva,
         "n_on": S.RETORNO_MIN_N_ON, "curva_fecha": fecha(S.CURVA_ON_FECHA), "n_on_total": len(S.CURVA_ON),
         "n_predictoras": len(M.NUMERICAS + M.CATEGORICAS + M.DUMMIES),
         "fecha_scraping": fecha(str(df.fecha_scraping.min())),
         "fecha_scraping_fin": fecha(str(df.fecha_scraping.max()))}

    # --- 1. Comprar o no (P1) --------------------------------------------------
    sens_d = leer("decision_sensibilidad.csv")
    pres = ok[ok.en_presupuesto]
    r.update(
        neta_med=ok.rent_neta_pct.median(), bruta_med=ok.rent_bruta_pct.median(),
        tir_med=ok.tir_5a_pct.median(), brecha_piso=piso - ok.rent_neta_pct.median(),
        neta_sobre_piso=(ok.rent_neta_pct >= piso).mean() * 100,
        n_pres=len(pres), n_fuera_soporte=int((pres.en_presupuesto & ~pres.en_soporte_modelo).sum()),
        fuera_tipos=pres.loc[~pres.en_soporte_modelo, "tipo_familia"].value_counts().to_dict(),
        alq_casa=int(((df.operacion == "alquiler") & (df.tipo_familia == "casa")).sum()),
        alq_ph=int(((df.operacion == "alquiler") & (df.tipo_familia == "ph")).sum()),
        alq_depto=int(((df.operacion == "alquiler") & (df.tipo_familia == "departamento")).sum()),
        neta_min_med=u.neta_min_pct.median(), neta_u_med=u.rent_neta_pct.median(),
        n_p1=int(u.p1_comprar.sum()), n_p1e=int(u.p1_comprar_con_entrada.sum()),
        p1_central=int((u.rent_neta_pct > vara).sum()),
        p1_rel_m2=u.loc[u.p1_comprar, "m2_relativo_celda"].median(),
        sens_p1_min=int(sens_d.n_p1.min()), sens_p1_max=int(sens_d.n_p1.max()),
        sens_p1e_max_con=int(sens_d.loc[sens_d.entrada != "sin", "n_p1_con_entrada"].max()),
        sens_p1_margen1=int(sens_d.loc[(sens_d.parametro == "margen por liquidez") & (sens_d.margen == 1.0), "n_p1"].iloc[0]),
        sens_p1_piso=int(sens_d.loc[(sens_d.parametro == "banda de retorno") & (sens_d.umbral == piso), "n_p1"].iloc[0]),
        sens_p1_techo=int(sens_d.loc[(sens_d.parametro == "banda de retorno") & (sens_d.umbral == techo), "n_p1"].iloc[0]),
        n_escenarios=len(sens_d),
        h3_umbral=float(sens_d.loc[sens_d.parametro == "horizonte", "umbral"].iloc[0]),
        h3_anios=int(sens_d.loc[sens_d.parametro == "horizonte", "horizonte"].iloc[0]),
        h3_p1=int(sens_d.loc[sens_d.parametro == "horizonte", "n_p1"].iloc[0]),
        h3_p1e=int(sens_d.loc[sens_d.parametro == "horizonte", "n_p1_con_entrada"].iloc[0]),
        sin_entrada_p1e=int(sens_d.loc[(sens_d.parametro == "costos de entrada") & (sens_d.entrada == "sin"),
                                       "n_p1_con_entrada"].iloc[0]),
        suba_p1e={x: int(sens_d.loc[(sens_d.parametro == "suba por refaccion") & (sens_d.suba == x),
                                    "n_p1_con_entrada"].iloc[0]) for x in S.SENSIBILIDAD_SUBA_REFACCION},
        n_precio_no_total=int((pres.en_presupuesto & pres.en_soporte_modelo & ~pres.precio_es_total).sum()),
        n_excluidas=int(df.excluida_revision.sum()),
        n_alerta_p1=int(u.loc[u.p1_comprar, "alerta_revision"].notna().sum()),
        n_alerta_p1e=int(u.loc[u.p1_comprar_con_entrada, "alerta_revision"].notna().sum()),
        repago_med=ok.meses_repago.median(), horizonte=S.HORIZONTE_ANIOS,
    )
    r["recupero_horizonte"] = S.HORIZONTE_ANIOS * 12 / r["repago_med"] * 100

    # --- 2. Costos de entrada y ABL ----------------------------------------------
    ad = leer("antes_despues_kpis.csv").set_index("escenario")
    q = pd.qcut(ok.alquiler_est_usd_mes * 12 / ok.venta_usd, 5, labels=False)
    abl_q = ok.groupby(q).abl_pct.median()
    r.update(neta_antes=ad.iloc[0].mediana_pct, neta_segm=ad.iloc[1].mediana_pct, tir_ad=ad.iloc[2].mediana_pct,
             barrios_antes=int(ad.iloc[0].barrios_sobre_piso), barrios_tir=int(ad.iloc[2].barrios_sobre_piso),
             entrada_med=ok.costos_entrada_pct.median(), abl_plano=S.ABL_PCT,
             abl_q1=abl_q.iloc[0], abl_q5=abl_q.iloc[-1],
             brecha_tir=piso - ok.tir_5a_pct.median())
    # Refaccion contra el descuento de H3 (notebook 02).
    ventas_all = df[(df.operacion == "venta") & df.venta_m2_usd.notna()]
    t3 = eda.efecto_estratificado(ventas_all, "a_reciclar", "venta_m2_usd", ESTRATO, S.MIN_GRUPO_ESTRATO)
    d = -eda.mediana_ponderada(t3.diferencia / t3.mediana_0, t3.peso)
    umbral = d / (1 - d) * 100
    rec = ok[ok.a_reciclar == 1]
    for esc, clave in [("base", "ref_min"), ("alto", "ref_int")]:
        c = C.refaccion_usd(rec, esc) / rec.venta_usd * 100
        r[clave], r[f"{clave}_cubre"] = c.median(), (c < umbral).mean() * 100
    r["ref_umbral"] = umbral

    # --- 3. Que propiedad (P2) y el modelo --------------------------------------------
    lo, hi = u.neta_min_pct, u.neta_max_pct
    front = u[u.p2_no_dominada]
    cm = leer("comparacion_modelos.csv").groupby("modelo")[["r2_log", "error_mediano_pct"]].mean()
    cb = leer("cobertura_banda.csv").set_index("banda").cobertura
    r.update(pares=D.pares_distinguibles(lo, hi) * 100,
             pares_tramo=D.pares_distinguibles_por_grupo(lo, hi, u.superficie_rango) * 100,
             pares_barrio=D.pares_distinguibles_por_grupo(lo, hi, u.barrio) * 100, n_front=len(front),
             ancho_u=(hi - lo).median(), ancho_front=(front.neta_max_pct - front.neta_min_pct).median(),
             front_barrios=eda.nombres_barrio(front.barrio.value_counts().index[:3]),
             r2_ridge=cm.loc["ridge", "r2_log"], r2_ref=cm.loc["mediana barrio x tramo", "r2_log"],
             err_ridge=cm.loc["ridge", "error_mediano_pct"], err_ref=cm.loc["mediana barrio x tramo", "error_mediano_pct"],
             r2_mejor_alt=cm.drop(index=["ridge", "mediana barrio x tramo"]).r2_log.max(),
             cob_antes=cb["anterior"] * 100, cob_ahora=cb["vigente"] * 100,
             sens_pares_min=sens_d.pares_distinguibles_pct.min(), sens_pares_max=sens_d.pares_distinguibles_pct.max())
    liq = leer("estadistica_ciudad_tiempo_publicacion.csv", E)
    liq = liq[liq.trimestre == liq.trimestre.max()].set_index("ambientes").dias
    r.update(liq_14_min=liq.drop(index=["Total", "5 ambientes y más"]).min(),
             liq_14_max=liq.drop(index=["Total", "5 ambientes y más"]).max(), liq_5=liq["5 ambientes y más"])

    # --- 4. Que rinde mas: tests formales y micro-mercados --------------------------------
    modelo = joblib.load(os.path.join(P, "modelo_alquiler.joblib"))
    fac = M.factores_suba_refaccion(modelo["pipeline"])
    alq = df[df.operacion == "alquiler"]
    r.update(suba_base=(fac[S.SUBA_REFACCION] - 1) * 100, suba_modelo=(fac["modelo"] - 1) * 100,
             n_alq=len(alq.dropna(subset=["alquiler_usd_mes", "sup_total_m2", "barrio"])),
             n_alq_reciclar=int((alq.a_reciclar == 1).sum()), n_alq_reciclado=int((alq.reciclado == 1).sum()),
             coef_reciclar=(fac["reciclado"] / fac["modelo"] - 1) * 100)
    r.update(V.resumen_hipotesis(df, factor_a_reciclar=fac["modelo"] / fac["reciclado"]))
    mc = SI.mca(SI.tabla_mca(df))
    df = df.copy()   # tras sumar columnas de a una, pandas avisa que el frame esta fragmentado
    df["grupo"] = SI.micromercados(mc["filas"])
    df["micromercado"] = df.grupo.map(SI.nombrar(df))
    ref = "departamento estandar"
    pv = SI.prima_en_celda(df[df.operacion == "venta"], "venta_m2_usd", "micromercado", ref)
    pa = SI.prima_en_celda(df[df.operacion == "alquiler"], "alquiler_m2_usd_mes", "micromercado", ref)
    torre = "torre con amenities"
    rel = (1 + pa.loc[torre, "prima_pct"] / 100) / (1 + pv.loc[torre, "prima_pct"] / 100) - 1
    r.update(mm_venta=pv.loc[torre, "prima_pct"], mm_venta_ic=(pv.loc[torre, "ic_inf"], pv.loc[torre, "ic_sup"]),
             mm_alq=pa.loc[torre, "prima_pct"], mm_alq_ic=(pa.loc[torre, "ic_inf"], pa.loc[torre, "ic_sup"]),
             mm_pp=rel * ok.rent_bruta_pct.median(), mm_share=(df.micromercado == torre).mean() * 100)

    # --- 5. Temporal (P3) ------------------------------------------------------------------
    tv = leer("temporal_vs_tradicional.csv")
    p3 = leer("decision_p3.csv")
    p3b = p3[p3.vacancia_tradicional_pct == S.VACANCIA_PCT].set_index(["gestion", "ocupacion_sostenible_pct"]).gana_temporal
    r.update(tv_celdas=len(tv), tv_equil_med=tv.ocupacion_equilibrio_pct.median(),
             tv_equil_auto=tv.ocupacion_equilibrio_auto_pct.median(), tv_ocup_med=tv.ocupacion_mediana_pct.median(),
             tv_gana_base=int(tv.gana_temporal_base.sum()), ocup_ref=S.OCUPACION_REF_PCT,
             tv_gana_ref=int(p3b[("tercerizada", S.OCUPACION_REF_PCT)]),
             tv_gana_ref_auto=int(p3b[("autogestionado", S.OCUPACION_REF_PCT)]))

    # --- 6. Sesgo de la cartera -----------------------------------------------------------
    sp, sr = leer("sesgo_precio_barrio.csv"), leer("sesgo_representacion_comuna.csv")
    r.update(sp_celdas=len(sp), sp_barato=(sp.desvio_pct < 0).mean() * 100,
             sp_pond=np.average(sp.desvio_pct, weights=sp.n_remax),
             sp_med_usado=sp[sp.estado == "usado"].desvio_pct.median(),
             sp_med_nuevo=sp[sp.estado == "estrenar"].desvio_pct.median(),
             sr_sobre=sr.loc[sr.indice_venta > 1.25, "comuna"].tolist(),
             sr_sub=sr.loc[sr.indice_venta < 0.75, "comuna"].tolist(),
             sr_reasignar=(sr.pct_cartera_venta - sr.pct_departamentos_ciudad).abs().sum() / 2)
    r["neta_a_precio_mercado"] = r["neta_med"] * (1 + r["sp_pond"] / 100)

    # --- 7. Accesibilidad (H2) --------------------------------------------------------------
    geo = df[df.dist_transporte_m.notna()]
    radio = S.RADIO_CAMINATA_M
    por_comuna = geo.groupby("comuna").agg(subte=("dist_subte_m", lambda s: (s <= radio).mean() * 100),
                                          red=("dist_transporte_m", lambda s: (s <= radio).mean() * 100))
    r.update(radio=radio, acc_subte=(geo.dist_subte_m <= radio).mean() * 100,
             acc_red=(geo.dist_transporte_m <= radio).mean() * 100,
             comunas_sin_subte=[int(c) for c in por_comuna.index[por_comuna.subte == 0]],
             red_sin_subte_min=por_comuna.loc[por_comuna.subte == 0, "red"].min(),
             red_sin_subte_max=por_comuna.loc[por_comuna.subte == 0, "red"].max())

    # --- Contexto de liquidez y credito -------------------------------------------------------
    tpub = leer("estadistica_ciudad_tiempo_publicacion.csv", E)
    tot = tpub[tpub.ambientes == "Total"].set_index("trimestre").dias
    col = leer("colegio_escribanos_mensual.csv", E)
    a25 = col[col.mes.str.startswith("2025")]
    r.update(liq_trim=tpub.trimestre.max(), liq_dias=float(tot[tpub.trimestre.max()]),
             hip_2025=a25.hipotecas.sum() / a25.compraventas.sum() * 100)
    r["liq_meses"] = r["liq_dias"] / 30.4
    r["r2_modelo"] = modelo["metadata"]["metricas_validacion"]["r2_log"]

    # --- Credito y espacios verdes (credito_y_verdes.py) ----------------------------------
    cv = leer("credito_verdes.csv").set_index("medida")
    r.update(cred_ventas=cv.loc["proporcion apto credito: ventas", "valor"],
             cred_u=cv.loc["proporcion apto credito: universo de la decision", "valor"],
             cred_p1=cv.loc["proporcion apto credito: P1: pasan sin costos de entrada", "valor"],
             cred_m2=cv.loc["m2 apto contra no apto, misma celda (%)", "valor"],
             cred_m2_p=cv.loc["m2 apto contra no apto, misma celda (%)", "p_valor"])
    for nombre in ("plaza", "parque"):
        for esp, clave in (("barrio + controles, ", nombre), ("barrio + controles, deptos, ", f"{nombre}_deptos")):
            fila = cv[cv.index.str.startswith(f"{nombre}, {esp}") & (cv.index.str.contains("deptos") == ("deptos" in esp))].iloc[0]
            r[clave] = {"tramo": fila.name.split(", ")[-1].split(" contra")[0], "valor": fila["valor"],
                        "ic": (fila["ic_inf"], fila["ic_sup"])}
    return r


# --------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------

def informe(r: dict) -> str:
    L = []
    w = L.append
    w("# Informe de hallazgos")
    w("")
    w("**TP Integrador · 82.04 Analítica Descriptiva (ITBA) · Grupo 2**")
    w("")
    w(f"*Generado por `py src/reporte.py` el {datetime.now():%d-%m-%Y}. Cada cifra de este documento se calcula "
      f"al generarlo a partir de `data/processed/` y `data/external/`: si se reejecuta el pipeline, el informe "
      f"se regenera con los números nuevos.*")
    w("")
    w("**Cliente:** un pequeño inversor con ahorros en dólares que compra **una sola unidad** en CABA para "
      f"alquilarla, con un presupuesto de {usd(S.PRESUPUESTO_MIN_USD)} a {usd(S.PRESUPUESTO_MAX_USD)} y un horizonte "
      f"de {r['horizonte']} años. **Base:** {num(r['n_ok'])} departamentos, casas y PH en venta de la cartera de "
      f"RE/MAX, relevados entre el {r['fecha_scraping']} y el {r['fecha_scraping_fin']}, con alquiler estimado "
      f"confiable. **Vara:** la TIR de las obligaciones negociables corporativas en dólares al plazo del inversor, "
      f"**{pct(r['vara'], 2)}**: la mediana de las {r['n_on']} ON bullet que vencen en {r['horizonte'] - 1} a "
      f"{r['horizonte'] + 1} años (banda p25 a p75: {pct(r['piso'], 2)} a {pct(r['techo'], 2)}), con precios de "
      f"mercado del {r['curva_fecha']}. La curva completa sube con el plazo: "
      + ", ".join(f"{pct(v, 2)} a {h} año{'s' if h > 1 else ''}" for h, v in r["curva"].items()) + ".")
    w("")
    w("Los hallazgos van ordenados por cuánto cambian la decisión del inversor, y cada uno cierra con la "
      "decisión que modifica. Solo quedan los que la cambian.")
    w("")
    w("---")
    w("")

    # 1
    no = r["neta_med"] < r["piso"]
    w("## 1. Para la propiedad típica, la decisión es " + ("no comprar" if no else "comprar"))
    w("")
    w(f"La rentabilidad **neta** mediana es **{pct(r['neta_med'], 2)}**, {pp(abs(r['brecha_piso']), signo=False)} "
      f"{'por debajo' if no else 'por encima'} del piso de la banda. Solo el {pct(r['neta_sobre_piso'])} de las "
      f"propiedades lo supera, y eso con la estimación central del alquiler.")
    w("")
    w(f"La función de decisión (P1) es más exigente: recomienda comprar solo si la neta del **escenario "
      f"pesimista** (el alquiler del percentil 10 de la banda de cada propiedad) supera la **vara**. Sobre las "
      f"{num(r['n_u'])} propiedades del universo de la decisión (dentro del presupuesto, con estimación confiable, "
      f"en el soporte del modelo y con un precio publicado que es el total):")
    w("")
    w("| | Propiedades | % del universo |")
    w("|---|---|---|")
    w(f"| Neta central sobre la vara | {num(r['p1_central'])} | {pct(r['p1_central'] / r['n_u'] * 100)} |")
    w(f"| **Neta pesimista sobre la vara (P1)** | **{num(r['n_p1'])}** | **{pct(r['n_p1'] / r['n_u'] * 100)}** |")
    w(f"| TIR pesimista a {r['horizonte']} años, con costos de entrada, sobre la vara | {num(r['n_p1e'])} | "
      f"{pct(r['n_p1e'] / r['n_u'] * 100, 2)} |")
    w("")
    w(grafico(13, "p1_neta_pesimista", "Neta pesimista contra la vara de retorno"))
    w("")
    w(f"**Las que pasan son baratas para su celda.** Su m² cuesta una mediana de {num(r['p1_rel_m2'], 2)} veces el "
      f"mediano de su barrio y tramo de superficie. Puede ser una oportunidad o algo que el aviso no dice (estado, uso, "
      f"ubicación): la función las señala para verificar, no para comprar a ciegas.")
    w("")
    w(f"**Precio total y revisión a mano.** El universo deja afuera {num(r['n_precio_no_total'])} ventas dentro del "
      f"presupuesto con financiación del vendedor o en pozo: el precio publicado suele ser solo la parte al contado, "
      f"y una unidad en pozo no se alquila hasta la entrega. Además, las listas se leyeron aviso por aviso: "
      f"{r['n_excluidas']} quedaron afuera por ser oficinas o de uso mixto, y {r['n_alerta_p1']} de las {r['n_p1']} "
      f"de P1 ({r['n_alerta_p1e']} de las {r['n_p1e']} que pasan con costos de entrada) llevan una alerta que hay "
      f"que verificar antes de decidir (`data/reference/revision_listas.csv`).")
    w("")
    w(f"**El soporte del modelo.** El universo excluye {num(r['n_fuera_soporte'])} propiedades dentro del "
      f"presupuesto, todas PH y casas. Hay {r['alq_casa']} alquileres observados de casas y {r['alq_ph']} de PH, "
      f"contra {num(r['alq_depto'])} de departamentos, y sin ese filtro la primera recomendación era una casa de 9 "
      f"ambientes con un alquiler extrapolado de más de USD 5.000. Las casas y los PH no se pueden recomendar con "
      f"estos datos.")
    w("")
    w(f"**Es robusto en la conclusión, no en la lista.** En los {r['n_escenarios']} escenarios de sensibilidad "
      f"(vacancia, gastos, ABL, costos de entrada, refacción, suba por refacción, banda de retorno, horizonte y "
      f"margen por liquidez), las que pasan P1 van de {r['sens_p1_min']} a {r['sens_p1_max']}; con costos de "
      f"entrada, nunca más de {r['sens_p1e_max_con']}. Con un margen por liquidez de 1 punto pasan "
      f"{r['sens_p1_margen1']}; con la vara en el p25 de la banda, {r['sens_p1_piso']}, y en el p75, "
      f"{r['sens_p1_techo']}. A {r['h3_anios']} años la vara baja a {pct(r['h3_umbral'], 2)} y pasan "
      f"{r['h3_p1']}, pero con costos de entrada {r['h3_p1e']}: con menos años, los costos pesan más.")
    w("")
    w(f"**Tampoco lo resuelve el horizonte.** Con un repago mediano de {num(r['repago_med'])} meses, en "
      f"{r['horizonte']} años el alquiler devuelve el {pct(r['recupero_horizonte'], 0)} del precio. El resto depende "
      f"de revender, en un mercado donde en 2025 solo el {pct(r['hip_2025'])} de las compraventas de la Ciudad se "
      f"hizo con hipoteca, y donde en el {trimestre(r['liq_trim'])} un aviso pasaba en promedio "
      f"{num(r['liq_dias'])} días publicado, unos {num(r['liq_meses'], 1)} meses (IDECBA, toda la Ciudad).")
    w("")
    w("> **Decisión que cambia.** La respuesta a \"¿compro para alquilar?\" es **no** para la propiedad típica: "
      "la renta fija en dólares le gana en retorno, liquidez y riesgo de gestión. Comprar se justifica solo para "
      "las pocas unidades que superan la vara aun en el escenario pesimista, después de verificar por qué son "
      "baratas, o como una apuesta explícita a la revalorización, declarada como tal.")
    w("")

    # 2
    w(f"## 2. Con los costos de comprar, la distancia a la renta fija pasa de {num(abs(r['brecha_piso']), 2)} a "
      f"{num(abs(r['brecha_tir']), 2)} puntos")
    w("")
    w(f"Comprar cuesta una mediana de **{pct(r['entrada_med'], 2)} del precio** entre comisión, escribano, "
      f"registrales y la mitad del Impuesto de Sellos (piso de cada rango publicado). Se pagan una vez y no vuelven "
      f"al vender, así que la cifra comparable con una ON es la **TIR a {r['horizonte']} años**, que los incluye.")
    w("")
    w("| | Mediana | Barrios sobre el piso |")
    w("|---|---|---|")
    w(f"| Neta, ABL plano | {pct(r['neta_antes'], 2)} | {r['barrios_antes']} |")
    w(f"| Neta, ABL segmentado | {pct(r['neta_segm'], 2)} | {r['barrios_antes']} |")
    w(f"| **TIR a {r['horizonte']} años, ABL segmentado + costos de entrada** | **{pct(r['tir_ad'], 2)}** | "
      f"**{r['barrios_tir']}** |")
    w("")
    w(grafico(5, "neta_tir_contra_banda", "Neta y TIR contra la banda de retorno"))
    w("")
    w(f"El **ABL segmentado** (Ley Tarifaria 2026, por barrio, superficie y tipo) casi no mueve el nivel, pero "
      f"redistribuye: pesa {pct(r['abl_q1'], 2)} del alquiler en el quintil que menos rinde y {pct(r['abl_q5'], 2)} "
      f"en el que más, contra un {pct(r['abl_plano'], 2)} plano para todos. Los **costos de entrada** sí mueven la "
      f"conclusión: la distancia de la mediana al piso pasa de {pp(abs(r['brecha_piso']), signo=False)} a "
      f"{pp(abs(r['brecha_tir']), signo=False)}.")
    w("")
    w(f"**La refacción.** Las unidades a reciclar cotizan con descuento (H3, hallazgo 4), equivalente a "
      f"{pct(r['ref_umbral'])} del precio de la unidad. Una refacción mínima (baño, cocina, pintura) cuesta una "
      f"mediana de {pct(r['ref_min'])} y el descuento la cubre en el {pct(r['ref_min_cubre'], 0)} de las unidades; "
      f"una integral cuesta {pct(r['ref_int'])} y no la cubre en {'ninguna' if r['ref_int_cubre'] == 0 else pct(r['ref_int_cubre'], 0) + ' de ellas'}.")
    w("")
    w(f"**Cuánto sube el alquiler al refaccionar es un supuesto.** El modelo diría {pct(r['suba_modelo'], 1, True)}, "
      f"pero esa cifra se apoya en un coeficiente de `a_reciclar` estimado con {r['n_alq_reciclar']} alquileres a "
      f"reciclar de {num(r['n_alq'])}: los avisos de alquiler casi nunca lo dicen. El caso base toma solo lo que "
      f"cobra de más un aviso reciclado, {pct(r['suba_base'], 1, True)}, estimado con {r['n_alq_reciclado']} "
      f"alquileres. Las que pasan P1 con costos de entrada son {r['suba_p1e']['sin']} sin suba, "
      f"{r['suba_p1e']['reciclado']} con el caso base y {r['suba_p1e']['modelo']} con el efecto completo: la "
      f"recomendación no depende de ese coeficiente. En el escenario sin costos de entrada la obra se sigue pagando "
      f"(pasan {r['sin_entrada_p1e']}).")
    w("")
    sobre = r["barrios_tir"]
    w("> **Decisión que cambia.** El hallazgo 1 era optimista: sin los costos de entrada, la renta parecía más "
      "cerca de la ON de lo que está. "
      + ("Ningún barrio supera el piso de la banda a cinco años." if sobre == 0 else
         f"Solo {sobre} barrio{'s' if sobre > 1 else ''} supera{'n' if sobre > 1 else ''} el piso de la banda a "
         f"cinco años.")
      + " Una unidad a reciclar es oportunidad solo si la obra es menor.")
    w("")

    # 3
    w("## 3. No hay una \"mejor propiedad\": la banda de error no deja elegir")
    w("")
    w(f"El modelo de alquiler (Ridge, {r['n_predictoras']} predictoras) le gana con claridad a una referencia simple, la mediana "
      f"del barrio y el tramo de superficie: R² de {num(r['r2_ridge'], 3)} contra {num(r['r2_ref'], 3)}, y error "
      f"relativo mediano de {pct(r['err_ridge'])} contra {pct(r['err_ref'])}, fuera de muestra en tres semillas. "
      f"Ninguna alternativa le gana a él (la mejor llega a {num(r['r2_mejor_alt'], 3)}). Su banda del percentil 10 "
      f"al 90 cubre el {pct(r['cob_ahora'])} de los avisos de alquiler de RE/MAX fuera de muestra (no se midió "
      f"sobre contratos ni sobre otros portales); la banda anterior, el error mediano de cada tramo, cubría el "
      f"{pct(r['cob_antes'])}.")
    w("")
    w(f"Con esa banda, P2 recomienda A sobre B solo si la neta pesimista de A supera la optimista de B. **Eso pasa "
      f"en el {pct(r['pares'])} de los pares**, en el {pct(r['pares_tramo'])} si se comparan unidades del mismo "
      f"tramo de superficie y en el {pct(r['pares_barrio'])} dentro del mismo barrio. En los {r['n_escenarios']} "
      f"escenarios de sensibilidad queda entre {pct(r['sens_pares_min'])} y {pct(r['sens_pares_max'])}.")
    w("")
    w(grafico(14, "p2_bandas_top30", "Bandas de las 30 propiedades mejor rankeadas"))
    w("")
    w(f"Ninguna propiedad supera con claridad a otras {num(r['n_front'])}, que forman la **frontera** de P2. Entre "
      f"ellas ninguna se distingue de otra, y pesan los barrios de m² barato ({lista(r['front_barrios'])}). Su "
      f"banda mediana es de {pp(r['ancho_front'], signo=False)}, contra {pp(r['ancho_u'], signo=False)} en el "
      f"universo: parte de la frontera está ahí porque el modelo sabe poco de esas propiedades, no porque rindan "
      f"más. La liquidez no desempata: el tiempo de publicación de IDECBA va de {num(r['liq_14_min'])} a "
      f"{num(r['liq_14_max'])} días entre 1 y 4 ambientes ({num(r['liq_5'])} con 5 o más), y no existe por barrio.")
    w("")
    w("> **Decisión que cambia.** P2 no devuelve \"la mejor propiedad\" sino una lista corta. Un ranking "
      "propiedad por propiedad sería más preciso que el dato que lo sostiene. Dentro de la lista, el criterio que "
      "informa es el **ancho de la banda**: entre dos candidatas, la de banda más angosta tiene una rentabilidad "
      "que se conoce mejor.")
    w("")

    # 4
    w("## 4. Qué rinde más, comparando propiedades semejantes")
    w("")
    w("Los cuatro tests, declarados junto con α = 0,05 antes de correrlos. Con miles de "
      "observaciones casi todo es significativo, así que cada uno se lee por el tamaño del efecto y por si cambia "
      "la decisión.")
    w("")
    w(f"- **El barrio es la palanca más fuerte (H1).** Cada USD 500 más de m² del barrio resta "
      f"{pp(abs(r['h1_efecto']), signo=False)} de rentabilidad bruta (IC 95% {ic(r['h1_ic'], 2, ' pp')}; Spearman "
      f"{num(r['h1_rho'], 2)} sobre {r['h1_barrios']} barrios, p {pval(r['h1_p'])}). Se sostiene en "
      f"{r['h1_tramos_rechazan']} de {r['h1_tramos']} tramos de superficie, después de corregir por comparaciones "
      f"múltiples.")
    w(f"- **Las torres nuevas con amenities rinden menos.** La síntesis de atributos (PCA y MCA) separa la oferta en "
      f"cuatro micro-mercados. Contra un departamento estándar del mismo barrio, tamaño y tipo, la \"torre con "
      f"amenities\" ({pct(r['mm_share'], 0)} de los avisos) cuesta {pct(r['mm_venta'], 0, True)} por m² (IC "
      f"{ic(r['mm_venta_ic'], 0, '%')}) y se alquila {pct(r['mm_alq'], 0, True)} (IC {ic(r['mm_alq_ic'], 0, '%')}): "
      f"unos {pp(abs(r['mm_pp']), 1, signo=False)} menos de bruta. Se mide con precios y alquileres publicados, "
      f"no con la rentabilidad estimada.")
    w(f"- **A reciclar: descuento real, oportunidad condicionada (H3).** Cotizan {pct(r['h3_precio'], 1)} por m² "
      f"contra sus comparables (IC {ic(r['h3_precio_ic'], 1, '%')}, p {pval(r['h3_p_precio'])}) y rinden "
      f"{pp(r['h3_renta'])} de bruta (IC {ic(r['h3_renta_ic'], 2, ' pp')}). El precio es observado; la renta, "
      f"estimada, y el modelo les resta {pct(abs(r['coef_reciclar']), 1)} por el coeficiente de `a_reciclar`, que "
      f"sale de {r['n_alq_reciclar']} alquileres. Sin ese coeficiente rendirían {pp(r['h3_renta_sin_coef'])}: la "
      f"diferencia de renta es una estimación frágil. Ver la refacción en el hallazgo 2.")
    w(f"- **Lo viejo rinde algo más, pero poco (H4).** Cada década de antigüedad baja el m² de venta "
      f"{pct(abs(r['h4_venta']))} y el alquiler {pct(abs(r['h4_alquiler']))} (p {pval(r['h4_p'])}): "
      f"{pp(r['h4_bruta_pp'])} de bruta por década, menos de un punto en 40 años.")
    w("")
    w(grafico(9, "h1_por_tramo", "H1 por tramo de superficie"))
    w("")
    w(grafico(12, "micromercados_prima", "Prima de cada micro-mercado en venta y alquiler"))
    w("")
    w("> **Decisión que cambia.** Dentro del presupuesto, buscar en barrios de m² barato y evitar las torres "
      "nuevas con amenities: lo que se paga de más al comprar no vuelve en el alquiler. Pagar amenities es una "
      "decisión de consumo, no de inversión. Las unidades a reciclar valen la pena solo con obra menor.")
    w("")

    # 5
    w("## 5. Alquilar por noche no rescata la inversión, salvo autogestionado")
    w("")
    w(f"Neta contra neta, en {r['tv_celdas']} celdas de barrio y dormitorios. La **ocupación de equilibrio**, con la "
      f"que el temporal empata al tradicional, tiene una mediana de **{pct(r['tv_equil_med'])}** con gestión "
      f"tercerizada y {pct(r['tv_equil_auto'])} autogestionado. Con la ocupación que estima Inside Airbnb "
      f"({pct(r['tv_ocup_med'])} de mediana) el temporal gana en {r['tv_gana_base']} celdas. Con el "
      f"{pct(r['ocup_ref'], 0)} que informa la prensa, gana en {r['tv_gana_ref']} con gestión tercerizada y en "
      f"{r['tv_gana_ref_auto']} autogestionado.")
    w("")
    w(grafico(15, "p3_ocupacion", "Celdas donde gana el temporal según la ocupación"))
    w("")
    w("> **Decisión que cambia (P3).** Tradicional, salvo para un inversor que opere el temporal por su cuenta y "
      "tenga evidencia de poder sostener más de la mitad del año ocupado. Autogestionar es un trabajo, no un "
      "ahorro, y las dos ocupaciones de referencia son estimaciones.")
    w("")

    # 6
    barato = r["sp_pond"] < 0
    w("## 6. La cartera de RE/MAX publica " + ("más barato" if barato else "más caro") + " que el mercado")
    w("")
    w(f"Contra el precio publicado del m² de IDECBA en la misma celda de barrio, ambientes y estado, RE/MAX publica "
      f"más barato en el {pct(r['sp_barato'], 0)} de {r['sp_celdas']} celdas: {pct(r['sp_pond'], 1, True)} en "
      f"promedio ponderado ({pct(r['sp_med_usado'], 1, True)} en usados, {pct(r['sp_med_nuevo'], 1, True)} a "
      f"estrenar). La cartera sobrerrepresenta {'la comuna' if len(r['sr_sobre']) == 1 else 'las comunas'} "
      f"{lista(r['sr_sobre'])} y subrepresenta {'la comuna' if len(r['sr_sub']) == 1 else 'las comunas'} "
      f"{lista(r['sr_sub'])} contra el stock del Censo 2022. Comprando al precio promedio del mercado, la neta "
      f"mediana bajaría de {pct(r['neta_med'], 2)} a alrededor de {pct(r['neta_a_precio_mercado'], 2)}.")
    w("")
    w("> **Decisión que cambia.** Los niveles de rentabilidad son los de la cartera, no los de CABA, y "
      f"probablemente están del lado {'alto' if barato else 'bajo'}: la brecha contra la renta fija del hallazgo 1 "
      "es, si algo, mayor. El análisis sirve para **comparar** propiedades, no para prometer una rentabilidad.")
    w("")

    # 7
    w("## 7. La cercanía al transporte ya está en el precio del barrio (H2, reformulada)")
    w("")
    w(f"Con subte, tren y Metrobús, el {pct(r['acc_red'])} de los avisos tiene una estación a menos de "
      f"{num(r['radio'])} m, contra el {pct(r['acc_subte'])} con el subte solo. En las comunas "
      f"{lista(r['comunas_sin_subte'])}, sin ninguna boca de subte a esa distancia, la red combinada llega a entre "
      f"el {pct(r['red_sin_subte_min'], 0)} y el {pct(r['red_sin_subte_max'], 0)}.")
    w("")
    w(f"Dentro del mismo barrio y con controles del inmueble, la pendiente lineal del m² con la distancia **no es "
      f"significativa** ({pct(r['h2_lineal_pct'], 1, True)} por km, p {pval(r['h2_lineal_p'])}, errores agrupados por "
      f"barrio). Lo que aparece es un escalón: **más allá de 1 km de la red, el m² vale "
      f"{pct(abs(r['h2_escalon_pct']))} menos** (IC {ic(r['h2_escalon_ic'], 1, '%')}, p {pval(r['h2_escalon_p'])}). "
      f"Afecta al {pct(r['h2_lejos_pct'], 0)} de los avisos. Es un resultado **exploratorio**: el corte de 1 km se "
      f"eligió mirando estos mismos datos, y su p-valor no descuenta esa búsqueda. Hay que confirmarlo con datos "
      f"nuevos antes de usarlo.")
    w("")
    w(grafico(3, "h2_perfil_distancia", "Precio del m² por tramo de distancia a la red"))
    w("")
    w("> **Decisión que cambia, poco.** Dentro de su barrio, el inversor no tiene que pagar una prima por estar al "
      "lado de una estación: hasta 1 km la distancia no se paga. Lejos de la red hay un descuento chico en pocos "
      "avisos, y el modelo de alquiler no muestra que el alquiler caiga en la misma proporción.")
    w("")

    # 8: credito y verdes
    pq, pl = r["parque_deptos"], r["plaza"]
    distingue = lambda x: x["ic"][0] > 0 or x["ic"][1] < 0
    w(f"## 8. {pct(r['cred_ventas'], 0)} de la oferta se declara apta para crédito, y la cercanía a un espacio verde "
      + ("no se distingue en el precio" if not (distingue(pq) or distingue(pl)) else "se paga poco"))
    w("")
    w(f"**Aptas para crédito.** Lo declara el {pct(r['cred_ventas'], 1)} de las ventas, el {pct(r['cred_u'], 1)} del "
      f"universo de la decisión y el {pct(r['cred_p1'], 1)} de las que pasan P1. Es un piso: un aviso que no lo "
      f"dice puede ser apto. Para el inversor importa por la salida: una unidad apta se puede revender a quien "
      f"compra con hipoteca, en un mercado donde en 2025 el {pct(r['hip_2025'])} de las compraventas se hizo así. "
      f"Contra sus comparables de la misma celda, el m² de las aptas cotiza {pct(r['cred_m2'], 1, True)} "
      f"(p {pval(r['cred_m2_p'])}); es una asociación, que puede venir de lo que la celda no controla (antigüedad, "
      f"estado, quién publica). Ser apta no encarece la compra.")
    w("")
    w(f"**Espacios verdes.** Con el método de H2 (barrio fijo, controles del inmueble y de la distancia a la red, "
      f"errores agrupados por barrio), estar a {pl['tramo']} de una plaza se asocia con un m² "
      f"{pct(pl['valor'], 1, True)} contra estar a más de 500 m (IC 95% {ic(pl['ic'], 1, '%')}). Estar a "
      f"{pq['tramo']} de un parque, en departamentos, {pct(pq['valor'], 1, True)} contra más de 1 km (IC 95% "
      f"{ic(pq['ic'], 1, '%')}; con todas las tipologías, {pct(r['parque']['valor'], 1, True)}, IC "
      f"{ic(r['parque']['ic'], 1, '%')}). Son asociaciones entre avisos del mismo barrio, y se prueban varios tramos "
      f"sin corregir por comparaciones múltiples.")
    w("")
    w("> **Decisión que cambia, poco.** Priorizar unidades aptas para crédito no cuesta más y facilita la reventa. "
      "La cercanía a una plaza no justifica pagar más; la de un parque, a lo sumo unos puntos, con evidencia débil. "
      "Ninguna de las dos entra en el modelo de alquiler.")
    w("")

    # Hipotesis
    w("## Estado de las hipótesis")
    w("")
    w("| Hipótesis | Test | Resultado | Efecto (IC 95%) | ¿Cambia la decisión? |")
    w("|---|---|---|---|---|")
    w(f"| **H1.** La rentabilidad cae con el precio del m² del barrio | Spearman con permutación; por tramo con Holm | "
      f"Se sostiene (p {pval(r['h1_p'])}) | {pp(r['h1_efecto'])} por USD 500/m² {ic(r['h1_ic'], 2)} | Sí |")
    w(f"| **H2.** El m² cae con la distancia al transporte | Efectos fijos de barrio, errores agrupados | Lineal: no "
      f"(p {pval(r['h2_lineal_p'])}). Escalón a 1 km, exploratorio (p {pval(r['h2_escalon_p'])}). **Se reformula** | "
      f"{pct(r['h2_escalon_pct'], 1, True)} {ic(r['h2_escalon_ic'], 1, '%')} | Poco |")
    w(f"| **H3.** Las unidades a reciclar cotizan con descuento | Van Elteren por celda barrio × superficie | Se sostiene "
      f"para el precio (p {pval(r['h3_p_precio'])}); la renta es estimada | {pct(r['h3_precio'], 1)} del m² "
      f"{ic(r['h3_precio_ic'], 1, '%')} | Sí, con obra menor |")
    w(f"| **H4.** La antigüedad pesa más en venta que en alquiler | Wald, bootstrap por celdas | Se sostiene "
      f"(p {pval(r['h4_p'])}) | {pp(r['h4_bruta_pp'])} de bruta por década | Poco |")
    w("")
    w("Desarrollo completo en `notebooks/04_validacion.ipynb`.")
    w("")

    # Lo que se dejo afuera
    w("## Hallazgos exploratorios que no se sostienen")
    w("")
    w("- **El mapa por zonas (norte, centro, sur y oeste).** Lo resume H1, que lo contrasta formalmente y en "
      "unidades del inversor.")
    w("- **La dispersión dentro de cada barrio.** Era el argumento para comparar unidades y no barrios. Ahora lo "
      "responde P2 con la banda de cada propiedad (hallazgo 3).")
    w("- **Las unidades chicas rinden más.** No tiene contraste formal, y la frontera de P2 muestra que el tamaño "
      "se confunde con la incertidumbre del modelo en las unidades grandes. No cambia la decisión de forma "
      "defendible.")
    w("")

    # Limites
    w("## Lo que este informe no permite afirmar")
    w("")
    w("- **Precios de cierre.** Todos los precios son de publicación, del lado de la venta y del alquiler.")
    w("- **El mercado de CABA.** Se describe la cartera de una red inmobiliaria, con el sesgo del hallazgo 6.")
    w("- **Una rentabilidad exacta.** Cada estimación tiene su banda: los KPIs por propiedad son rangos.")
    w("- **Casas y PH.** Quedan fuera de las recomendaciones: el modelo casi no tiene alquileres observados de ellos.")
    w("- **Retorno total.** Solo se mide renta; la apreciación requiere una serie temporal. La TIR supone reventa "
      "al mismo precio en dólares y no incluye costos de salida.")
    w("- **Riesgo legal.** Desalojos, impagos y cambios de régimen no tienen una fuente que los cuantifique: es una "
      "limitación declarada y todo resultado es optimista en esa medida.")
    w("- **Liquidez por propiedad.** El tiempo de publicación es de toda la Ciudad, por cantidad de ambientes.")
    w("- **Causalidad.** Comparar dentro del estrato controla por zona, tamaño y tipología, no por todo.")
    w("")
    w("Los supuestos están en `src/supuestos.py` con su fuente y fecha, y las fuentes externas en "
      "`informe/FUENTES_EXTERNAS.md`. Cada hallazgo se desarrolla en los notebooks 01 a 06.")
    w("")
    return "\n".join(L)


README = "README.md"
MARCA_INICIO = "<!-- hallazgos:inicio (lo escribe py src/reporte.py; no editar a mano) -->"
MARCA_FIN = "<!-- hallazgos:fin -->"


def hallazgos_readme(r: dict) -> str:
    """Los hallazgos en pocas lineas, con las mismas cifras del informe, para el README."""
    pq = r["parque_deptos"]
    return "\n".join([
        f"1. **Para la propiedad típica, la decisión es no comprar.** La neta mediana ({pct(r['neta_med'], 2)}) "
        f"queda debajo de la renta fija en dólares al mismo plazo ({pct(r['vara'], 2)}, la TIR de las ON que "
        f"vencen en {r['horizonte'] - 1} a {r['horizonte'] + 1} años). Con los costos de comprar, la TIR a "
        f"{r['horizonte']} años mediana es {pct(r['tir_med'], 2)}.",
        f"2. **Pocas propiedades le ganan a la ON aun en el escenario pesimista**: {num(r['n_p1'])} de "
        f"{num(r['n_u'])} del universo, y {num(r['n_p1e'])} con costos de entrada. Son más baratas que su "
        f"celda y se leyeron a mano: {r['n_excluidas']} se excluyeron por ser oficinas o de uso mixto, y "
        f"{r['n_alerta_p1e']} de las {num(r['n_p1e'])} finales llevan una alerta para verificar.",
        f"3. **No hay una \"mejor propiedad\".** Solo el {pct(r['pares'])} de los pares se distingue con la "
        f"banda de error: P2 devuelve una lista de {num(r['n_front'])} propiedades, no un ranking.",
        f"4. **El barrio es la palanca más fuerte**: cada USD 500 más de m² del barrio resta "
        f"{pp(abs(r['h1_efecto']), signo=False)} de rentabilidad bruta (H1). Las torres nuevas con amenities "
        f"cuestan {pct(r['mm_venta'], 0)} más por m² y se alquilan solo {pct(r['mm_alq'], 0)} más.",
        f"5. **El temporal no rescata la inversión** salvo autogestionado: necesita una ocupación de "
        f"{pct(r['tv_equil_med'])} con gestión tercerizada y {pct(r['tv_equil_auto'])} autogestionado.",
        f"6. **La cercanía al transporte ya está en el precio del barrio**: hasta 1 km no se paga; más allá, "
        f"un descuento de {pct(abs(r['h2_escalon_pct']))} que es exploratorio (H2, reformulada).",
        f"7. **{pct(r['cred_ventas'], 0)} de la oferta se declara apta para crédito, y la cercanía a un "
        f"espacio verde se paga poco.** "
        f"Estar cerca de una plaza no se distingue en el precio; de un parque, "
        f"{pct(pq['valor'], 1, True)} en departamentos (IC 95% {ic(pq['ic'], 1, '%')}), evidencia débil.",
    ])


def actualizar_readme(r: dict, ruta: str = README) -> bool:
    """Reemplaza el bloque entre las marcas del README. Sin marcas, no toca nada."""
    if not os.path.exists(ruta):
        return False
    texto = open(ruta, encoding="utf-8").read()
    if MARCA_INICIO not in texto or MARCA_FIN not in texto:
        return False
    antes, resto = texto.split(MARCA_INICIO, 1)
    _, despues = resto.split(MARCA_FIN, 1)
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write(antes + MARCA_INICIO + "\n\n" + hallazgos_readme(r) + "\n\n" + MARCA_FIN + despues)
    return True


def main() -> int:
    requeridos = [os.path.join(P, f) for f in [
        "dataset_analitico.csv", "antes_despues_kpis.csv", "comparacion_modelos.csv", "cobertura_banda.csv",
        "decision_sensibilidad.csv", "decision_p3.csv", "temporal_vs_tradicional.csv", "sesgo_precio_barrio.csv",
        "sesgo_representacion_comuna.csv", "modelo_alquiler.joblib"]]
    requeridos += [os.path.join(E, "colegio_escribanos_mensual.csv"),
                   os.path.join(E, "estadistica_ciudad_tiempo_publicacion.csv")]
    faltan = [f for f in requeridos if not os.path.exists(f)]
    if faltan:
        print(f"Faltan insumos: {faltan}")
        print("Correr antes el pipeline completo (ver README, Reproducir)")
        return 1
    r = calcular()
    texto = informe(r)
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    print(f"Escrito {SALIDA} ({len(texto.splitlines())} lineas)")
    if actualizar_readme(r):
        print(f"Actualizados los hallazgos de {README}")
    print(f"    neta mediana {r['neta_med']:.2f}% contra piso {r['piso']:.2f}%; P1: {r['n_p1']} de {r['n_u']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
