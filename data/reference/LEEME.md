# Datos de referencia

`revision_listas.csv` es la revisión a mano de las listas de la decisión: una fila por
aviso leído, con la acción (`excluir` o `alertar`) y el motivo. La aplica
`src/decision.py`: los avisos con `excluir` salen del
universo y los que tienen `alertar` llevan su motivo al tablero.

Vale solo para los avisos de este relevamiento: con datos nuevos hay que repetir la
lectura.
