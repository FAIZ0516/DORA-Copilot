"""Zara Data Workspace endpoints (dataset discovery, workflows, charts).

Ported from F3, where these lived directly in ``main.py``. In this
architecture ``main.py`` is only a composition root, so request handling
belongs here alongside the other routers (AGENTS.md §4).

Read paths run against the governed read-only DoraDB session; only saved
workflow *definitions* are written, and those go to the separate writable
runtime store, never to DoraDB. Without this router the workspace frontend
silently falls back to its built-in mock dataset.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database.db import ZaraWorkflow, get_db
from ..database.doradb import DoraDbConfigurationError, doradb_session
from ..zara_workspace import (
    VisualizationQueryRequest,
    VisualizationRecommendRequest,
    WorkflowDefinition,
    WorkflowRunRequest,
    ZaraWorkspaceError,
    get_dataset_schema,
    get_dataset_values,
    list_datasets,
    query_visualization,
    recommend_visualizations,
    run_workflow,
)
from .dependencies import development_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["zara-workspace"])


def _zara_read(operation: Callable[[Session], Any]) -> Any:
    """Run one Zara operation against the governed read-only DoraDB session."""

    try:
        with doradb_session() as real_session:
            return operation(real_session)
    except ZaraWorkspaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DoraDbConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.warning("Zara DoraDB operation failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="DoraDB could not complete the workspace request."
        ) from exc


@router.get("/datasets")
def zara_datasets() -> list[dict[str, Any]]:
    return _zara_read(list_datasets)


@router.get("/datasets/{dataset_id}/schema")
def zara_dataset_schema(dataset_id: str) -> dict[str, Any]:
    return _zara_read(lambda session: get_dataset_schema(session, dataset_id))


@router.get("/datasets/{dataset_id}/values/{column_name}")
def zara_dataset_values(dataset_id: str, column_name: str) -> dict[str, list[Any]]:
    return _zara_read(
        lambda session: get_dataset_values(session, dataset_id, column_name)
    )


@router.post("/workflows/run")
def zara_run_workflow(request: WorkflowRunRequest) -> dict[str, Any]:
    return _zara_read(lambda session: run_workflow(session, request))


@router.post("/visualizations/query")
def zara_query_visualization(request: VisualizationQueryRequest) -> dict[str, Any]:
    return _zara_read(lambda session: query_visualization(session, request))


@router.post("/visualizations/recommend")
def zara_recommend_visualizations(
    request: VisualizationRecommendRequest,
) -> dict[str, list[dict[str, Any]]]:
    return _zara_read(lambda session: recommend_visualizations(session, request))


@router.post("/workflows")
def zara_save_workflow(
    workflow: WorkflowDefinition,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    saved = ZaraWorkflow(user_id=user_id, name=workflow.name, definition={})
    session.add(saved)
    session.flush()
    definition = workflow.model_dump(mode="json")
    definition["id"] = str(saved.id)
    saved.definition = definition
    session.commit()
    return definition


@router.put("/workflows/{workflow_id}")
def zara_update_workflow(
    workflow_id: UUID,
    workflow: WorkflowDefinition,
    user_id: str = Depends(development_session),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    if workflow.id is not None and workflow.id != workflow_id:
        raise HTTPException(status_code=400, detail="Workflow ID does not match the URL.")
    saved = session.get(ZaraWorkflow, workflow_id)
    if saved is None or saved.user_id != user_id:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    definition = workflow.model_dump(mode="json")
    definition["id"] = str(workflow_id)
    saved.name = workflow.name
    saved.definition = definition
    session.commit()
    return definition


__all__ = ["router"]
