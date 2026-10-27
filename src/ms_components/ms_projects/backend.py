"""Load MolSuite's default catalog only when a caller has not supplied a backend."""
from __future__ import annotations


def create_catalog_backend(*, app_id_filter: str | None = None):
    try:
        from ms_flow.core.project.catalog import ProjectCatalogBackend
    except ModuleNotFoundError as exc:
        if exc.name != "ms_flow":
            raise
        raise ModuleNotFoundError(
            'The project catalog requires ms_flow. Install it with: pip install "ms_components[projects]"',
            name="ms_flow",
        ) from exc
    return ProjectCatalogBackend(app_id_filter=app_id_filter)
