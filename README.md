# ¿Conviene comprar para alquilar? Rentabilidad inmobiliaria en CABA

**TP Integrador · 82.04 Analítica Descriptiva (ITBA) · Grupo 2 · 2026**

Iael Berezovsky · Nicolás Caveda · Máximo Lladhon · Ezequiel Naymark

Análisis de rentabilidad para un **pequeño inversor particular** que, con USD 80.000 a
200.000 en dólares, evalúa comprar **una** unidad en la Ciudad Autónoma de Buenos Aires
para alquilarla, con un horizonte de 5 años. La alternativa contra la que se mide es la
renta fija en dólares al mismo plazo. El trabajo responde tres decisiones: si comprar
(P1), qué propiedad (P2) y si alquilarla de forma tradicional o temporal (P3).

| Para el inversor | Dónde |
|---|---|
| **Tablero**: ¿conviene el mercado, dónde y qué mirar? | Versión publicada: *se completa al publicar la app desde este repositorio* ([cómo publicarlo](#publicarlo-en-streamlit-community-cloud)). Localmente: [El tablero](#el-tablero) |
| **Simulador**: ¿esta propiedad, a este precio? | [`simulador/simulador.html`](simulador/simulador.html): se descarga y se abre con doble clic |
| **Informe de hallazgos**, con cada cifra calculada en vivo | [`informe/INFORME_HALLAZGOS.md`](informe/INFORME_HALLAZGOS.md) |

---

## Hallazgos

Las cifras de esta sección las escribe `py src/reporte.py` a partir de
`data/processed/`, igual que el informe: no se editan a mano.

<!-- hallazgos:inicio (lo escribe py src/reporte.py; no editar a mano) -->

1. **Para la propiedad típica, la decisión es no comprar.** La neta mediana (5,65%) queda debajo de la renta fija en dólares al mismo plazo (6,26%, la TIR de las ON que vencen en 4 a 6 años). Con los costos de comprar, la TIR a 5 años mediana es 4,27%.
2. **Pocas propiedades le ganan a la ON aun en el escenario pesimista**: 93 de 3.766 del universo, y 12 con costos de entrada. Son más baratas que su celda y se leyeron a mano: 8 se excluyeron por ser oficinas o de uso mixto, y 3 de las 12 finales llevan una alerta para verificar.
3. **No hay una "mejor propiedad".** Solo el 7,2% de los pares se distingue con la banda de error: P2 devuelve una lista de 397 propiedades, no un ranking.
4. **El barrio es la palanca más fuerte**: cada USD 500 más de m² del barrio resta 0,98 pp de rentabilidad bruta (H1). Las torres nuevas con amenities cuestan 33% más por m² y se alquilan solo 17% más.
5. **El temporal no rescata la inversión** salvo autogestionado: necesita una ocupación de 65,5% con gestión tercerizada y 51,7% autogestionado.
6. **La cercanía al transporte ya está en el precio del barrio**: hasta 1 km no se paga; más allá, un descuento de 6,7% que es exploratorio (H2, reformulada).
7. **24% de la oferta se declara apta para crédito**, sin pagar más por m². Estar cerca de una plaza no se distingue en el precio; de un parque, +5,9% en departamentos (IC 95% [0,5%, 11,7%]), evidencia débil.

<!-- hallazgos:fin -->

---

## Seguimiento de la devolución

La única sección del repositorio que habla del proceso de corrección. Cada observación
se resolvió donde estaba el problema (datos, código, modelo o tablero), no solo en el
texto.

| Observación | Estado | Qué cambiamos | Dónde se verifica |
|---|---|---|---|
| **Revisar a mano las listas de P1 y P2**: precio de la candidata nº 1, usos mixtos u oficinas, señal de financiación | Resuelta | El precio de la candidata nº 1 pasa a ser el total (USD 85.000 + 65.000 de hipoteca privada), igual que otro aviso con "13 cuotas". Se amplió la minería de texto: "A refac." cuenta como a reciclar, y `en_pozo` y `financiacion` detectan "POZO", fecha de entrega futura, "N cuotas", anticipo y "ctas". El universo de la decisión deja afuera las ventas con financiación del vendedor o en pozo. Se leyeron a mano las finales de P1 y los primeros puestos de P2, y se buscaron señales de riesgo en el resto: las oficinas y los usos mixtos se excluyen con su motivo, y lo que hay que verificar lleva una alerta | `src/limpieza.py` (`CORREGIR_PRECIO_TOTAL_USD`), `src/variables.py` y sus regresiones en `src/test_variables.py`, `src/decision.py` (`universo`), [`data/reference/revision_listas.csv`](data/reference/revision_listas.csv), notebook 06 sección 1, tablero, pestaña *¿Qué comprar?* (columna ⚠ y ficha) |
| **Escenario "sin costos de entrada"**: cobraba el alquiler refaccionado sin pagar la obra; el test excluía esas unidades | Resuelta | Los costos de entrada y la refacción son parámetros separados: sin costos de entrada, la obra se sigue pagando. El test cubre las unidades a reciclar con un oráculo de valor presente y un negativo sintético | `src/decision.py` (`tir_pesimista`), `src/test_decision.py`, `data/processed/decision_sensibilidad.csv`, tablero, pestaña *Supuestos y alcance* |
| **El efecto de `a_reciclar` sale de 2 alquileres** y explicaba buena parte de la suba post-refacción | Resuelta: supuesto explícito con sensibilidad | La suba del alquiler al refaccionar es un supuesto: el efecto de `reciclado`, estimado con 131 alquileres. La decisión prueba sin suba y con el efecto completo del modelo, y no cambia. En H3 se informa el n y el efecto de la renta sin ese coeficiente | `src/supuestos.py` (`SUBA_REFACCION`), `src/modelo_alquiler.py` (`factores_suba_refaccion`), `src/kpis.py`, notebooks 02 (sección 3), 03 (sección 3), 04 (H3) y 06 (sección 5), informe, hallazgos 2 y 4 |
| **Claims del simulador**: "8 de cada 10 alquileres reales" y su uso con avisos de otros portales | Resuelta | La cobertura se informa como lo que es, cobertura fuera de muestra sobre avisos de alquiler de RE/MAX, y sale del modelo guardado. Se aclara que no se midió sobre contratos ni sobre otros portales | `simulador/simular.py`, `simulador/web/plantilla.html`, tablero (encabezado y limitaciones), [El simulador](#el-simulador) |
| **Comparar contra renta fija de distinta duration**, alineada con el horizonte, en lugar de una ON a 2037 | Resuelta | Curva de 31 ON bullet en dólares (YPF, Pampa, Pan American, Pluspetrol, TGS y Telecom) con precios de la API de data912.com y términos del reporte de ON de Criteria. La TIR se calcula en el código. La vara de P1 es la TIR a 5 años (± 1); la curva se informa a 1, 2, 3 y 5 años, y la sensibilidad prueba un horizonte de 3 años con la ON de 3 años | `src/curva_on.py`, `src/test_curva_on.py`, `data/external/on_terminos.csv` y `on_precios.csv`, `src/supuestos.py` sección 4, notebook 06 sección 0, tablero (barra lateral) |
| **Preguntas pendientes**: proporción de avisos aptos para crédito y prima por cercanía a espacios verdes | Resuelta | Proporción en las ventas, en el universo y en P1, y precio del m² contra comparables. Prima de plazas y parques con el método de H2 y errores agrupados | `src/credito_y_verdes.py`, notebook 01 sección 7, notebook 06 sección 6, informe, hallazgo 8 |
| **Un solo proyecto**, sin carpetas por entrega | Resuelta | Este repositorio contiene solo el proyecto final, con historial propio. Las etapas anteriores quedan en el repositorio de trabajo del grupo | Este repositorio |
| El escalón de H2 a 1 km se eligió con los mismos datos | Resuelta | Se presenta como resultado exploratorio | Informe, hallazgo 7 y tabla de hipótesis |
| Docstrings que prometían más que el código ("garantiza la cobertura") | Resuelta | Redactados según lo que el código hace | `src/modelo_alquiler.py` (`ajuste_conformal`) |
| Para portfolio: agrupar avisos duplicados en la validación cruzada, elegir la penalización cuantílica dentro de la validación anidada, cobertura de la banda por tramo de superficie, guardar el HTML de las publicaciones | No resuelta | Quedan como continuación. No cambian las conclusiones: la revisión a mano encontró un par de avisos duplicados en las listas finales y los marcó con una alerta | [Limitaciones](#limitaciones) |

---

## Cómo está organizado

| Carpeta | Qué hay |
|---|---|
| `src/` | El pipeline, los supuestos con su fuente (`supuestos.py`) y los tests |
| `notebooks/` | El análisis contado en orden, con cada gráfico entre su pregunta y su lectura |
| `data/raw/` | `dataset_maestro.csv`: el relevamiento de RE/MAX, sin modificar |
| `data/external/` | Tablas fechadas de las fuentes externas, capas espaciales y la curva de ON |
| `data/processed/` | `dataset_analitico.csv` (la matriz final), los reportes de cada script y el diccionario de datos |
| `data/reference/` | La revisión a mano de las listas y el ranking de barrios de la versión inicial |
| `informe/` | El informe de hallazgos (lo genera `reporte.py`) y el catálogo de fuentes externas |
| `tablero/` | El tablero en Streamlit |
| `simulador/` | El simulador: la página autocontenida y su versión por consola |
| `graficos/` | Los gráficos que guardan los notebooks |

### Los notebooks

Están guardados con sus salidas, así que se leen sin ejecutar nada.

| Notebook | La pregunta |
|---|---|
| [`01_accesibilidad`](notebooks/01_accesibilidad.ipynb) | ¿Qué tan conectada está cada propiedad a la red de transporte, el mercado lo paga en el precio, y se paga estar cerca de una plaza o un parque? |
| [`02_costos_del_propietario`](notebooks/02_costos_del_propietario.ipynb) | ¿Cuánto le queda al inversor después de los costos, y le gana a una ON? ABL segmentado, costos de entrada, refacción y TIR a 5 años |
| [`03_modelo_alquiler`](notebooks/03_modelo_alquiler.ipynb) | ¿Cuánto se puede confiar en el alquiler estimado? Comparación contra una referencia, qué paga el mercado y la banda de incertidumbre |
| [`04_validacion`](notebooks/04_validacion.ipynb) | ¿Qué hipótesis se sostienen con un contraste formal, con qué magnitud, y cuáles cambian la decisión? |
| [`05_sintesis_atributos`](notebooks/05_sintesis_atributos.ipynb) | ¿Se pueden resumir los atributos del aviso en pocos ejes, y hay tipos de propiedad que rinden distinto en el mismo barrio y tamaño? |
| [`06_decision`](notebooks/06_decision.ipynb) | ¿Conviene comprar, qué propiedad, y tradicional o temporal? La vara, la revisión de las listas, la función de decisión y su sensibilidad |

---

## El tablero

> **Tengo entre USD 80.000 y 200.000: ¿conviene comprar para alquilar, y si compro, qué?**

El tablero es la interfaz del inversor con el análisis. Cada pestaña responde una
pregunta suya, y todo lo que muestra sale de columnas ya calculadas en
`data/processed/dataset_analitico.csv`: la app filtra y resume, no recalcula ningún KPI,
así que cada número de la pantalla coincide con el del informe.

| Pestaña | La pregunta del inversor | Qué muestra |
|---|---|---|
| **¿Conviene comprar?** | ¿La propiedad típica le gana a la renta fija en dólares? | Neta mediana con su banda, TIR a 5 años, propiedades sobre el piso de la banda de retorno y cuántas pasan cada etapa de la decisión |
| **¿Dónde?** | ¿Qué barrios rinden más, y por qué? | Mapa coloreado por rentabilidad, neta y TIR por barrio con su banda, y la relación entre el m² del barrio y la rentabilidad (H1) |
| **¿Qué comprar?** | ¿Qué propiedades vale la pena mirar? | Las que pasan P1, rotuladas **"a verificar"** y con ⚠ si la revisión encontró algo; la frontera de P2 como rangos, ordenada por ancho de banda y no por rentabilidad; y la ficha de la propiedad elegida, con el motivo de la alerta y el link al aviso |
| **¿Tradicional o temporal?** | ¿Alquilar por noche cambia la respuesta? | En cuántas celdas gana el temporal según la ocupación, con gestión tercerizada y autogestionada |
| **Supuestos y alcance** | ¿Cuánto depende todo de los supuestos, y qué no se puede afirmar? | Cuántas propiedades pasan P1 en cada escenario de sensibilidad, las limitaciones y la fecha de cada fuente |

Un encabezado fijo indica cuántas propiedades quedan con los filtros, de qué cartera y en
qué fecha se relevaron, y muestra siempre tres limitaciones: son precios de publicación,
es una sola inmobiliaria, y cada rentabilidad es una banda. La barra lateral tiene los
filtros (presupuesto, tipo, comuna, barrio, ambientes, superficie, antigüedad y métrica)
y la vara de retorno, que es una referencia fija y no un filtro.

### Cómo abrirlo

Desde la raíz del repositorio:

```bash
py -m pip install -r requirements.txt     # una sola vez
py -m streamlit run tablero/app.py
```

Se abre en `http://localhost:8501`. Toma el tema de `.streamlit/config.toml` y lee el
dataset versionado, así que no hace falta correr el pipeline antes.

### Publicarlo en Streamlit Community Cloud

En <https://share.streamlit.io>, *Create app* desde este repositorio, rama `main`, con
**main file path** `tablero/app.py`. Community Cloud instala las dependencias del
`requirements.txt` de la raíz y lee el tema de `.streamlit/config.toml`.

`py tablero/test_tablero.py` verifica la lógica del tablero: sin filtros reproduce las
cifras del dataset leído directamente del CSV, cada filtro cumple la condición que dice
aplicar, y un filtro que deja cero filas no rompe nada.

---

## El simulador

> **Encontré esta propiedad: ¿a este precio me conviene?**

El análisis habla del mercado, pero el inversor compra una sola propiedad, y la que va a
mirar de verdad casi seguro no está en el relevamiento. El simulador le hace a cualquier
propiedad la misma evaluación que recibió cada venta del dataset: alquiler estimado con
su banda, ABL, neta, costos de entrada, TIR a 5 años, P1, su posición frente a la
frontera de P2 y P3. Usa el mismo modelo guardado y los mismos supuestos.

- **El precio lo carga el inversor**, y se toma como el precio total. Puede poner el que
  piensa ofrecer, o bajarlo hasta encontrar el precio a partir del cual la propiedad le
  gana a la vara: su **precio de reserva** para negociar.
- **Permite probar combinaciones**: cambiar solo el barrio o sumar una característica y
  ver cuánto se mueve el resultado.
- **La vacancia es del inversor**: quien ya tiene un inquilino en vista ve cómo cambia
  la conclusión.
- **Llega a quien decide**: es un solo archivo HTML, sin servidor ni internet, y la
  dirección de la página guarda la propiedad cargada para compartirla.

**Lo que no es.** No es un tasador. La banda del alquiler tiene una **cobertura fuera de
muestra medida sobre avisos de alquiler de RE/MAX**; no se midió sobre contratos ni sobre
avisos de otros portales. Para una propiedad de otro portal, el simulador da la misma
cuenta, pero su precisión no está verificada. Comprar sigue exigiendo mirar lo que el
aviso no dice: el estado real, las expensas, la documentación y por qué la propiedad está
más barata que su celda.

```bash
py simulador/simular.py                                                  # pregunta los datos
py simulador/simular.py --barrio caballito --m2 50 --ambientes 2 --venta 110000
```

`py simulador/test_simulador.py` pasa cada venta del dataset por el simulador y compara
cada cifra con la del pipeline (en las columnas de la decisión, donde no actúan los
filtros de precio total y revisión, que el simulador no puede conocer), y corre la página
en Chrome sin ventana para comparar el cálculo en JavaScript con el de Python.

---

## Métodos

Cada método se desarrolla en su notebook; acá van las decisiones que más pesan.

### La vara: renta fija en dólares al mismo plazo

La alternativa del inversor son las obligaciones negociables corporativas en dólares de
primera línea: con el mismo capital, en dólares y con riesgo argentino, igual que el
inmueble. `src/curva_on.py` arma una curva por plazo:

- **Instrumentos**: 31 ON bullet a tasa fija de YPF, Pampa, Pan American, Pluspetrol,
  TGS y Telecom. Solo bullet: con amortización parcial el plazo no es el vencimiento.
- **Términos** (cupón, frecuencia, vencimiento): transcriptos del *Reporte de
  Obligaciones Negociables 2T2026* de Criteria (`data/external/on_terminos.csv`).
- **Precios**: API pública de data912.com (`/live/arg_corp`, precios de BYMA en dólares
  MEP). La consulta se guarda con su fecha en `data/external/on_precios.csv`; con
  `--actualizar` se vuelve a consultar.
- **TIR**: efectiva anual, la misma convención que la TIR del inmueble. La API no dice
  si el precio incluye el cupón corrido; se tomó como precio limpio porque, con esa
  convención, la diferencia contra la TIR de Criteria no crece con el cupón corrido. La
  otra convención se informa como sensibilidad.
- **La vara de P1** es la mediana de las ON que vencen a 5 años ± 1; la banda que usa la
  sensibilidad va de su p25 a su p75.

### Accesibilidad y espacios verdes

`espacial.py` mide, para cada aviso, la distancia en línea recta a la estación más
cercana de subte, tren o Metrobús (`dist_transporte_m`), y a la plaza y al parque más
cercanos. H2 se estima con efectos fijos de barrio: sin el barrio, la distancia mide
centralidad. La medida no ve barreras, frecuencias ni destinos, y no incluye el
Premetro: se lee como una cota inferior del esfuerzo de llegar a la red (notebook 01).

### Costos del propietario

- **ABL segmentado** con la Ley Tarifaria 2026 (Ley 6927, arts. 41 a 45): Impuesto
  Inmobiliario progresivo, Tasa ABL con el coeficiente geográfico de cada barrio,
  recargo, mínimo y tope. La Valuación Fiscal Homogénea no se publica por partida: se
  aproxima como una proporción del m² de mercado de la zona, calibrada para que la
  unidad de referencia pague el porcentaje anterior. La fórmula reproduce los siete
  ejemplos de un calculador externo (`test_costos.py`).
- **Costos de entrada**, con el piso de cada rango publicado (el efecto que se informa
  es un mínimo):

| Costo | Base | Alto | Fuente |
|---|---|---|---|
| Comisión inmobiliaria del comprador | 3% | 4% | CUCICBA, 09-01-2026 (Ley 2340, mod. Ley 5859) |
| Escribano | 1% | 2% | La Nación, 01-05-2026 |
| Certificados, informes e inscripción | 0,2% | 0,4% | La Nación, 01-05-2026 |
| Impuesto de Sellos, mitad del comprador | 1,35% hasta ARS 226,1 millones; 1,75% arriba | ídem | Ley 6927, art. 34; La Nación, 01-05-2026 |
| Refacción de una unidad a reciclar | Baño USD 5.573 + cocina USD 6.220 + pintura | Integral, ARS 1.350.000/m² + IVA | Reporte Inmobiliario y Sui Color vía La Nación, 30-03-2026; RenovArqui, 02-2026 |

- **TIR a 5 años**: la tasa que iguala lo que se pone al comprar (precio, costos de
  entrada y refacción) con 5 años de alquiler neto y la reventa al mismo precio en
  dólares. Es la cifra comparable con la TIR de una ON del mismo plazo.
- **Suba del alquiler al refaccionar**: un supuesto, el efecto de `reciclado` en el
  modelo, porque el de `a_reciclar` sale de 2 alquileres. Se prueba sin suba y con el
  efecto completo.
- **Riesgo legal**: limitación declarada, sin número. No hay una fuente que publique la
  frecuencia o el costo de desalojos e impagos en CABA.

### El modelo de alquiler

Un Ridge sobre el logaritmo del alquiler, con 21 predictoras elegidas por disponibilidad
y sentido económico. Se compara fuera de muestra, en tres semillas, contra una referencia
simple (la mediana del barrio y tramo de superficie), contra la misma regresión con las
variables espaciales y contra gradient boosting. Una alternativa reemplaza al Ridge solo
si mejora el R² en 0,01 en todas las semillas, un criterio declarado antes de comparar;
ninguna lo cumple, y los coeficientes del Ridge se leen como cuánto paga el mercado por
cada característica. La **banda** de cada propiedad son los percentiles 10 y 90 de su
alquiler: regresión cuantílica calibrada por grupo de evidencia del barrio
(*conformalized quantile regression*). `modelo_alquiler.joblib` guarda la metadata y el
hash de los datos de entrenamiento, que `test_modelo.py` verifica (notebook 03).

### Hipótesis

Los cuatro tests se declararon antes de correrlos, con α = 0,05, y cada uno cierra con el
p-valor, el tamaño del efecto en unidades del inversor, un intervalo del 95% y si cambia
la decisión. Con miles de observaciones casi todo es significativo, así que se lee el
efecto (notebook 04 y tabla del informe).

| Hipótesis | Test |
|---|---|
| H1 — la rentabilidad cae con el precio del m² del barrio | Spearman unilateral con p-valor por permutación, repetido por tramo de superficie con Holm |
| H2 — el m² cae con la distancia al transporte | Regresión con efectos fijos de barrio y controles, errores agrupados por barrio |
| H3 — las unidades a reciclar cotizan con descuento | Van Elteren por celda barrio × tramo de superficie |
| H4 — la antigüedad pesa más en venta que en alquiler | Wald sobre dos regresiones con efectos fijos de celda, bootstrap por celdas |

### Síntesis de atributos

PCA y MCA sobre los atributos del aviso, y micro-mercados por k-medias. Es un análisis
informativo: no entra al modelo de alquiler porque no mejora el R² según el mismo
criterio (notebook 05). Su hallazgo, con precios observados, es que las torres nuevas
con amenities cuestan más por m² de lo que se alquilan de más.

### La función de decisión

`src/decision.py` implementa y evalúa las tres decisiones (notebook 06):

| Decisión | Criterio |
|---|---|
| **P1** — ¿comprar? | Neta del escenario pesimista (alquiler del percentil 10) sobre la vara; como versión estricta, la TIR pesimista a 5 años con costos de entrada |
| **P2** — ¿cuál? | A sobre B solo si sus bandas de neta no se superponen; la frontera son las que ninguna otra supera |
| **P3** — ¿tradicional o temporal? | El temporal, solo si la ocupación sostenible supera la de equilibrio de su celda |

El **universo** son las ventas con estimación confiable, dentro del presupuesto, en el
soporte del modelo (celdas tipo × tramo con al menos 30 alquileres observados: casas y PH
quedan afuera), con un precio publicado que es el total y que la revisión a mano no
excluyó. La **sensibilidad** mueve un supuesto por vez (vacancia, gastos, ABL, costos de
entrada, refacción, suba por refacción, banda de retorno, horizonte y margen por
liquidez) y dos extremos.

### Decisiones metodológicas

| Decisión | Por qué |
|---|---|
| La vara es la ON al plazo del inversor, no un bono más largo | Un bono más largo paga más por el plazo, no por ser mejor alternativa |
| P1 sobre el escenario pesimista; P2 por dominancia de bandas | Una compra no se deshace barato, y la banda es la incertidumbre real de cada estimación |
| Solo entran precios totales, y las listas finales se leen a mano | Un precio que es solo el contado, o una oficina, pasa cualquier filtro de rentabilidad |
| La suba por refacción es un supuesto con sensibilidad | El coeficiente del modelo se apoya en 2 alquileres |
| Los costos de entrada y la refacción son parámetros separados | Un escenario sin costos de entrada no puede cobrar la obra sin pagarla |
| H2 con efectos fijos de barrio y errores agrupados | Sin el barrio se mide centralidad; con el error común la pendiente parecía significativa y no lo es |
| El ABL segmentado se calibra a la unidad de referencia | Aísla la redistribución de un cambio de nivel, que se prueba aparte |
| El tablero no recalcula; el simulador sí, con el modelo guardado | Las cifras de la pantalla coinciden con el informe por construcción, y un test ata el simulador al dataset |
| El informe y los hallazgos del README los escribe un script | Cada cifra narrada sale del dato y no se desincroniza |

---

## Limitaciones

- **Precios de publicación, no de cierre**, del lado de la venta y del alquiler.
- **Una sola inmobiliaria**: la cartera de RE/MAX publica más barato que el mercado y
  está sesgada en cobertura geográfica (informe, hallazgo 6). Las rentabilidades
  probablemente están del lado alto.
- **El alquiler es estimado**: cada rentabilidad es una banda, cuya cobertura se midió
  fuera de muestra sobre avisos de alquiler de RE/MAX, no sobre contratos.
- **Casas y PH fuera de las recomendaciones**: hay muy pocos alquileres observados.
- **La revisión a mano es de las listas, no del universo**: se leyeron las finales y los
  primeros puestos, y el resto se revisó por palabras clave. La validación cruzada no
  agrupa avisos duplicados, y los links a RE/MAX dejan de funcionar cuando la propiedad se
  vende.
- **La vara depende de la fecha**: la curva de ON es la de la consulta guardada; con
  otra fecha, la vara cambia y hay que volver a correr el pipeline.
- **Sin apreciación, costos de salida ni riesgo legal**: la TIR supone reventa al mismo
  precio en dólares.
- **Liquidez de toda la Ciudad**: el tiempo de publicación de IDECBA es por cantidad de
  ambientes, no por barrio ni por propiedad.
- **Accesibilidad en línea recta**, sin barreras, frecuencias ni Premetro.
- **Un corte temporal único**: el relevamiento es de agosto de 2026.
- **Asociación, no causalidad**: los tests y las primas muestran relaciones, no qué las
  provoca.

---

## Reproducir

Python 3.13. Desde la raíz del repositorio:

```bash
py -m pip install -r requirements.txt

py src/limpieza.py --tc 1500             # crudo -> dataset limpio + auditoría
py src/variables.py                      # minería de texto con RegEx -> dummies
py src/espacial.py                       # distancias a subte, tren, Metrobús, plazas y parques
py src/curva_on.py                       # curva de ON con los precios guardados (--actualizar consulta la API)
py src/kpis.py                           # modelo de alquiler -> KPIs, ABL, costos y TIR
py src/temporal.py                       # P3: tradicional contra temporal
py src/sesgo.py                          # la cartera contra IDECBA y el Censo
py src/accesibilidad.py                  # H2: precio del m² y distancia a la red
py src/comparacion_modelos.py            # el modelo contra la referencia (el paso más lento)
py src/decision.py                       # P1 a P3 -> columnas de la decisión
py src/credito_y_verdes.py               # aptos para crédito y prima por espacios verdes
py src/reporte.py                        # informe y hallazgos de este README
py simulador/simular.py --actualizar     # parámetros del simulador
py simulador/simular.py --html           # la página del simulador
```

Los tests, que no modifican nada:

```bash
py src/test_variables.py      py src/test_supuestos.py     py src/test_fuentes.py
py src/test_eda.py            py src/test_espacial.py      py src/test_costos.py
py src/test_curva_on.py       py src/test_accesibilidad.py py src/test_modelo.py
py src/test_validacion.py     py src/test_sintesis.py      py src/test_decision.py
py src/test_credito_y_verdes.py
py tablero/test_tablero.py    py simulador/test_simulador.py
```

Después, los notebooks, que leen esas salidas (el 03 necesita `dataset_espacial.csv`,
que es intermedio y no se versiona):

```bash
cd notebooks
for n in 01_accesibilidad 02_costos_del_propietario 03_modelo_alquiler 04_validacion 05_sintesis_atributos 06_decision; do
  py -m nbconvert --to notebook --execute --inplace $n.ipynb
done
```

`espacial.py` y `curva_on.py` usan las capas y los precios versionados en
`data/external/`, así que corren sin red; `espacial.py --descargar` y
`curva_on.py --actualizar` vuelven a consultar las fuentes. El tablero y la página del
simulador no necesitan el pipeline. La parte del test del simulador que corre la página
necesita Chrome; sin él, se saltea.

Las fuentes externas, con su fecha y sus limitaciones, están en
[`informe/FUENTES_EXTERNAS.md`](informe/FUENTES_EXTERNAS.md), y cada columna del dataset,
en [`data/processed/DICCIONARIO_DATOS.md`](data/processed/DICCIONARIO_DATOS.md).

---

## Licencia

Ver [`LICENSE`](LICENSE).
