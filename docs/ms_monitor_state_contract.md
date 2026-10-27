# Contrato mínimo de estado para `ms_monitor`

## Objetivo

Definir el shape mínimo estable que la UI y futuros consumidores como AMDock pueden esperar de `ms_monitor`.

Este contrato no exige que el runtime deje de usar `dict` internamente. Exige que el bridge entregue modelos consistentes y que los campos críticos tengan semántica clara.

## Principios del contrato

- los modelos del monitor son la frontera estable para UI
- los campos obligatorios deben estar siempre presentes
- los campos opcionales deben tener semántica explícita
- los campos derivados deben poder recalcularse desde el snapshot sin ambigüedad

## `ProjectMonitorState`

### Rol

Snapshot canónico del proyecto activo observado por el monitor.

### Campos obligatorios

- `project_id: str | None`
- `project_name: str`
- `has_project: bool`
- `active: bool`
- `jobs_active: int`
- `job_ids: list[str]`
- `statuses: list[str]`
- `external_cancellers: int`
- `executors: list[ExecutorMonitorState]`
- `jobs: list[JobMonitorState]`
- `chunks: list[ChunkMonitorState]`
- `recent_events: list[EventMonitorState]`
- `health: RuntimeHealthState | None`
- `updated_at: datetime`

### Campos opcionales

- `project_path: str | None`

### Reglas

- si `has_project` es `False`, `project_id` debe ser `None`
- si `has_project` es `False`, `jobs`, `chunks` y `job_ids` deben venir vacíos
- `jobs_active` debe reflejar actividad operativa actual, no historial

## `JobMonitorState`

### Rol

Snapshot resumido y operativo de un job individual.

### Campos obligatorios

- `job_id: str`
- `status: str`
- `cancel_requested: bool`
- `progress: float`
- `chunks_total: int`
- `chunks_done: int`
- `chunks_failed: int`
- `chunks_stage_failed: int`
- `chunks_running: int`
- `chunks_pending: int`
- `chunks_staging: int`
- `feed_exhausted: bool`
- `feed_cursor_position: int`
- `feed_items_acked: int`
- `throughput_eps: float`
- `loop_latency_ms: float`
- `chunk_queue_wait_avg_s: float`
- `chunk_queue_wait_max_s: float`
- `chunks: list[ChunkMonitorState]`

### Campos opcionales

- `project_id: str | None`
- `origin_id: str`
- `task_type: str`
- `executor_name: str`
- `priority: int`
- `queue_policy: str`
- `job_queue_wait_s: float | None`
- `updated_at: datetime | None`
- `output_sink: dict[str, Any] | None`

### Derivados

- `is_terminal` deriva solo de `status`

### Reglas

- `job_id` nunca puede estar vacío
- `status` debe ser uno de los estados reconocidos por el monitor o un estado futuro que la UI trate como texto opaco
- `cancel_requested` y `status == "cancel_requested"` no son equivalentes, pero la UI puede mostrarlos juntos
- `chunks` debe contener solo chunks vivos o relevantes para detalle actual, no historial completo

## `ChunkMonitorState`

### Rol

Representación resumida de un chunk vivo o relevante en el monitor.

### Campos obligatorios

- `chunk_id: str`
- `job_id: str`
- `status: str`
- `progress: float`
- `executor_name: str`

### Reglas

- `chunk_id` nunca puede estar vacío
- `job_id` debe referenciar a un job presente o recientemente visible en el snapshot

## `EventMonitorState`

### Rol

Evento operativo reciente asociado al proyecto o a un job.

### Campos obligatorios

- `event_id: int`
- `job_id: str`
- `level: str`
- `event_type: str`
- `message: str`

### Campos opcionales

- `created_at: datetime | None`

### Reglas

- `event_id` debe ser monotónico dentro de una misma fuente
- `message` es texto de operador, no payload arbitrario serializado

## `ExecutorMonitorState`

### Rol

Resumen operativo por executor visible desde el runtime.

### Campos obligatorios

- `name: str`
- `backend: str`
- `mode: str`
- `shared_fs: bool`
- `integration: str`
- `remote_backend: bool`
- `local_resource_accounting: str`
- `locally_constrained: bool`
- `active_jobs: int`
- `running_chunks: int`
- `reserved_cpu: int`
- `health: dict[str, Any]`

### Campos opcionales

- `used_cpu: int | None`

### Reglas

- `name` nunca puede estar vacío
- `health` puede ser un shape flexible, pero debe seguir siendo un detalle complementario; no debe reemplazar campos operativos principales

## `RuntimeHealthState`

### Rol

Estado global del runtime para el proyecto actual.

### Campos obligatorios

- `status: str`
- `active_jobs: int`
- `loop_latency_ms: float`
- `checks: dict[str, Any]`
- `core_health: dict[str, Any]`
- `persistence_health: dict[str, Any]`
- `recovery_health: dict[str, Any]`
- `sink_health: dict[str, Any]`

### Campos opcionales

- `project_id: str | None`

### Reglas

- si `status == "inactive"`, el monitor puede seguir teniendo historial visible, pero no jobs activos
- `core_health`, `persistence_health`, `recovery_health` y `sink_health` son las categorías estables para semántica de health
- `checks` es compatibilidad y detalle auxiliar; la UI no debe depender de claves arbitrarias para su semántica principal

## Campos estables vs flexibles

### Estables

Estos campos deben considerarse contrato del monitor:

- identidad de proyecto
- identidad de job
- estado de job
- progreso
- contadores de chunks
- health global
- categorías de health (`core`, `persistence`, `recovery`, `sink`)
- resumen por executor
- eventos recientes

### Flexibles

Estos campos pueden evolucionar sin romper la UI si hay defaults razonables:

- `health.checks`
- `ExecutorMonitorState.health`
- `output_sink`
- campos adicionales futuros de scheduler o retry

## Contrato operativo mínimo del bridge

El bridge debe poder garantizar:

- `refresh_now()` retorna `ProjectMonitorState | None`
- `current_snapshot` refleja el último snapshot emitido
- `get_recent_events(job_id=None)` retorna `list[EventMonitorState]`
- `get_recent_outputs(job_id, limit=...)` retorna lista ordenada de outputs recientes
- las señales se emiten con objetos compatibles con estos modelos

## Capacidades que no forman parte de este contrato

No son parte del contrato mínimo de estado:

- edición de jobs
- borrado de jobs
- retry o resubmit
- acceso a logs completos de backend remoto

Esas capacidades deben definirse como contrato operativo aparte si se agregan.
