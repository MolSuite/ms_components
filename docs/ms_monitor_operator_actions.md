# Politica de acciones de operador en `ms_monitor`

## Objetivo

Definir qué acciones de operador están soportadas hoy por `ms_monitor`, con qué contrato, y qué acciones quedan explícitamente fuera.

La regla es simple:

- solo se soportan acciones con backend claro y semántica defendible
- lo no soportado se declara como tal
- la UI no debe inventar mutaciones que el runtime no garantiza

## Acciones soportadas

### `refresh` / `resync`

Estado: soportada

Ruta:

- `MolSuiteMonitorBridge.resync_now()`
- `MolSuiteMonitorBridge.refresh_now()`

Semántica:

- fuerza reconstrucción del snapshot actual
- actualiza estado visible de sincronización
- no modifica jobs

### `cancel_job`

Estado: soportada

Ruta:

- `MolSuiteMonitorBridge.cancel_job(job_id)`
- backend real: `MolSuite.cancel_job(job_id)`

Semántica:

- solo aplica a jobs visibles y no terminales
- la acción solicita cancelación; no garantiza terminación instantánea
- errores se emiten de forma controlada vía señales del bridge

## Acciones soportadas de forma condicional

### `resubmit_job`

Estado: soportada con restricciones

Ruta:

- `MolSuiteMonitorBridge.resubmit_job(job_id)`
- backend real: `MolSuite.resubmit_job(job_id)`

Restricciones:

- se considera solo para jobs terminales
- puede fallar si el job original no tiene fuente persistida rehidratable
- `ms_monitor` no oculta esa restricción; la expone como error controlado

Lectura pragmática:

`resubmit_job` existe porque el runtime ya lo soporta. No equivale a “retry mágico” para cualquier job.

## Acciones no soportadas

### `delete_job`

Estado: no soportada

Motivo:

- no existe una política formal de borrado/archivo de historial
- borrar desde monitor sin esa política arriesga incoherencias de persistencia y UX

### `archive_job`

Estado: no soportada

Motivo:

- hoy no hay semántica explícita de archivo separada del estado durable normal

### `edit_job`

Estado: no soportada

Motivo:

- editar un job ya enviado no tiene semántica firme en el runtime
- si hace falta variar parámetros, la ruta correcta es plantilla nueva o `resubmit` cuando aplique

### `retry_job`

Estado: no soportada como acción independiente

Motivo:

- el runtime no expone hoy un contrato separado de retry manual distinto de `resubmit`

## Señales y visibilidad operativa

El bridge expone visibilidad de operación mediante:

- `sync_state_updated`
- `operator_action_succeeded`
- `operator_action_failed`
- `bridge_error`

Eso permite que la UI:

- muestre último resync
- muestre errores de sincronización
- muestre si una acción fue aceptada o rechazada

## Decisión arquitectónica

`ms_monitor` no debe convertirse en una consola administrativa general del executor.

Su papel es:

- observar
- diagnosticar
- ejecutar un conjunto pequeño de acciones seguras

Cuando una acción no cumple esas condiciones, debe declararse fuera de alcance en vez de implementarse a medias.
