# Baseline de `ms_monitor`

## Alcance del baseline

Este baseline describe el estado real de `src/molsuite_components/ms_monitor/` en el código actual, con foco en:

- fuentes de datos
- acoplamientos
- superficie pública del bridge
- capacidades realmente disponibles
- riesgos estructurales inmediatos

No describe el objetivo futuro del monitor. Describe lo que hoy existe.

## Estructura actual

`ms_monitor` tiene `1307` líneas en `12` módulos Python.

Distribución principal:

- `polling.py`: `354` líneas
- `widget.py`: `288` líneas
- `bridge.py`: `116` líneas
- `models.py`: `113` líneas
- resto de módulos: `12` a `96` líneas

Lectura pragmática:

- la estructura de archivos es razonable
- la complejidad real está concentrada en `polling.py` y `widget.py`
- el problema actual no es monolito por tamaño, sino contrato y acoplamiento

## Fuentes de datos actuales

### Fuente primaria

El poller usa principalmente una instancia de `MolSuite`:

- `molsuite.get_project_activity()`
- `molsuite.get_runtime_healthcheck()`
- `molsuite.executor_manager.get_status()`
- `molsuite.executor_manager.list_jobs()`
- `molsuite.executor_manager.get_job(job_id)`

### Fuente secundaria

El bridge usa rutas auxiliares para outputs:

- `molsuite.executor_access.list_job_outputs(...)` si existe
- `molsuite.get_job_outputs(job_id)` como fallback

### Fuente de acciones

La cancelación actual va directa al manager:

- `molsuite.executor_manager.cancel_job(job_id)`

## Superficie pública actual del monitor

`MolSuiteMonitorBridge` expone hoy:

- `start()`
- `stop()`
- `refresh_now()`
- `get_recent_events(job_id=None)`
- `get_recent_outputs(job_id, limit=...)`
- `cancel_job(job_id)`

Señales Qt:

- `project_changed`
- `project_cleared`
- `project_snapshot_updated`
- `job_upserted`
- `job_removed`
- `job_finished`
- `executors_updated`
- `health_updated`
- `events_updated`
- `bridge_error`

## Modelos actuales

El monitor ya tiene modelos dataclass tipados:

- `ProjectMonitorState`
- `JobMonitorState`
- `ChunkMonitorState`
- `EventMonitorState`
- `ExecutorMonitorState`
- `RuntimeHealthState`

Eso es una buena base. El problema no es falta de modelos, sino que gran parte del poller sigue normalizando desde `dict` crudos del runtime en línea.

## Acoplamientos principales

### Acoplamientos aceptables

- dependencia del monitor en `MolSuite`
- dependencia del widget en el bridge y en modelos tipados
- uso de señales Qt para desacoplar polling y UI

### Acoplamientos a reducir

- `polling.py` depende directo de `executor_manager`
- `polling.py` depende de shapes crudos de `get_status()`, `list_jobs()` y `get_job()`
- `bridge.cancel_job()` depende directo de `executor_manager`
- `bridge.get_recent_outputs()` mezcla dos rutas de acceso sin contrato formal del orden de preferencia

### Síntoma práctico

El monitor ya no está acoplado a SQL crudo, pero todavía depende demasiado de shapes del runtime que no están formalizados como contrato específico para monitor.

## Uso actual de datos crudos

Hoy el monitor trata respuestas crudas de dict en varios puntos:

- `health_raw.get(...)`
- `status_raw.get(...)`
- `item.get(...)` para executors
- `summary.get(...)` para jobs resumidos
- `raw.get(...)` para detalle de job

Eso no rompe funcionalidad, pero vuelve frágil la evolución del monitor porque el contrato efectivo vive implícito dentro de `polling.py`.

## Estado funcional actual

Lo que sí funciona hoy:

- detectar ausencia de proyecto activo
- detectar cambio de proyecto
- construir snapshot del proyecto activo
- mostrar jobs del proyecto activo
- mostrar health del runtime
- mostrar resumen de executors
- mostrar chunks vivos
- mostrar eventos recientes
- mostrar outputs recientes
- refresco manual
- cancelación básica desde UI

## Matriz de capacidades actual

| Capacidad | Estado | Observación |
| --- | --- | --- |
| Monitoreo de proyecto activo | soportada | `refresh_now()` y polling funcionales |
| Listado de jobs | soportada | activos + recientes, con retención acotada |
| Detalle básico por job | soportada | vía snapshot, chunks, eventos y outputs recientes |
| Healthcheck runtime | soportada | vía `get_runtime_healthcheck()` |
| Resumen por executor | soportada | vía `manager.get_status()` |
| Eventos recientes | soportada | disponibles desde el snapshot actual |
| Outputs recientes | parcial | dos rutas backend, sin contrato único explícito |
| Refresh manual | soportada | expuesto en bridge y widget |
| Cancelación | parcial | funciona, pero depende de `executor_manager` directo |
| Historial reciente | parcial | existe retención de jobs terminales recientes, pero no hay política formal de historial |
| Logs de job | parcial | hoy se aproximan con eventos/outputs; no hay contrato explícito de logs |
| Borrado de jobs | no soportada | no hay ruta canónica en el bridge |
| Edición de jobs | no soportada | no hay semántica pública definida |
| Resubmit/retry desde monitor | requiere API | no debe inventarse desde UI |

## Cobertura actual

La suite `tests/test_molsuite_monitor_bridge.py` ya cubre lo esencial:

- sin proyecto activo
- proyecto activo y cambio de proyecto
- staging y chunks vivos
- cancelación observada
- orden de jobs activos y terminales recientes
- eventos recientes por job
- outputs recientes

Lectura pragmática:

- la base funcional existe
- la deuda está más en el contrato y en las acciones de operador que en la ausencia total de comportamiento

## Riesgos actuales

- que cambios en shapes internos del runtime rompan `polling.py`
- que la cancelación siga atada a internals en vez de una ruta soportada
- que outputs, eventos y logs se mezclen semánticamente
- que el historial crezca sin política explícita
- que AMDock termine consumiendo detalles no canónicos del bridge

## Conclusión

`ms_monitor` ya es usable como monitor básico. No está “roto” en lo esencial.

Lo que falta no es rehacerlo desde cero, sino formalizarlo:

- contrato de datos del monitor
- contrato de capacidades soportadas
- reducción del acoplamiento a `executor_manager`
- separación más clara entre observar, diagnosticar y actuar
