from unittest.mock import MagicMock, patch

import pytest

from backend.zara_workspace import (
    ColumnMetadata,
    DatasetMetadata,
    VisualizationQueryRequest,
    WorkflowDefinition,
    ZaraWorkspaceError,
    _load_catalog,
    compile_workflow,
    query_visualization,
)


def _catalog() -> dict[str, DatasetMetadata]:
    dataset = DatasetMetadata(
        id="enp.tbl_gdt_dte_jira_issues",
        schema_name="enp",
        table_name="tbl_gdt_dte_jira_issues",
        relation_type="table",
        approximate_rows=100,
        columns=(
            ColumnMetadata("key", "character varying", False),
            ColumnMetadata("status", "character varying", True),
            ColumnMetadata("dcpsquad", "character varying", True),
            ColumnMetadata("story_points", "integer", True),
            ColumnMetadata("created", "timestamp without time zone", True),
        ),
    )
    return {dataset.id: dataset}


def _workflow(*, filter_value: str = "Done") -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "name": "Open Jira issues",
            "nodes": [
                {
                    "id": "dataset-1",
                    "type": "dataset",
                    "config": {"dataset": "enp.tbl_gdt_dte_jira_issues"},
                    "position": {"x": 0, "y": 0},
                },
                {
                    "id": "filter-1",
                    "type": "filter",
                    "config": {
                        "match": "all",
                        "rules": [
                            {
                                "id": "rule-1",
                                "column": "status",
                                "operator": "not_equals",
                                "value": filter_value,
                            }
                        ],
                    },
                    "position": {"x": 1, "y": 0},
                },
                {
                    "id": "select-1",
                    "type": "select",
                    "config": {
                        "columns": [
                            "key",
                            "status",
                            "dcpsquad",
                            "story_points",
                            "created",
                        ]
                    },
                    "position": {"x": 2, "y": 0},
                },
                {
                    "id": "output-1",
                    "type": "output",
                    "config": {},
                    "position": {"x": 3, "y": 0},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "dataset-1", "target": "filter-1"},
                {"id": "edge-2", "source": "filter-1", "target": "select-1"},
                {"id": "edge-3", "source": "select-1", "target": "output-1"},
            ],
        }
    )


def test_workflow_filter_values_are_parameterized() -> None:
    malicious = "Done' OR TRUE --"
    compiled = compile_workflow(_workflow(filter_value=malicious), _catalog())
    assert malicious not in compiled.sql
    assert malicious in compiled.params.values()
    assert '"enp"."tbl_gdt_dte_jira_issues"' in compiled.sql


def test_workflow_rejects_an_unapproved_dataset() -> None:
    workflow = _workflow()
    workflow.nodes[0].config["dataset"] = "public.unapproved_table"
    with pytest.raises(ZaraWorkspaceError, match="not approved"):
        compile_workflow(workflow, _catalog())


def test_catalog_hides_sensitive_jira_fields() -> None:
    session = MagicMock()
    object_result = MagicMock()
    object_result.mappings.return_value.all.return_value = [
        {
            "schema_name": "enp",
            "table_name": "tbl_gdt_dte_jira_issues",
            "relation_type": "table",
            "approximate_rows": 10,
        }
    ]
    column_result = MagicMock()
    column_result.mappings.return_value.all.return_value = [
        {
            "schema_name": "enp",
            "table_name": "tbl_gdt_dte_jira_issues",
            "column_name": "status",
            "data_type": "character varying",
            "nullable": True,
        },
        {
            "schema_name": "enp",
            "table_name": "tbl_gdt_dte_jira_issues",
            "column_name": "assignee",
            "data_type": "character varying",
            "nullable": True,
        },
        {
            "schema_name": "enp",
            "table_name": "tbl_gdt_dte_jira_issues",
            "column_name": "root_cause",
            "data_type": "character varying",
            "nullable": True,
        },
        {
            "schema_name": "enp",
            "table_name": "tbl_gdt_dte_jira_issues",
            "column_name": "labels",
            "data_type": "json",
            "nullable": True,
        },
    ]
    session.execute.side_effect = [object_result, column_result]
    catalog = _load_catalog(session)
    assert [column.name for column in catalog["enp.tbl_gdt_dte_jira_issues"].columns] == [
        "status"
    ]


def test_visualization_query_groups_the_prepared_output() -> None:
    request = VisualizationQueryRequest.model_validate(
        {
            "workflow": _workflow().model_dump(mode="json"),
            "group_by": "status",
            "value": None,
            "calculation": "count",
            "filters": [{"column": "dcpsquad", "operator": "contains", "value": "Atlas"}],
            "limit": 50,
        }
    )
    session = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {"label": "In Progress", "value": 7, "row_count": 10},
        {"label": "Blocked", "value": 3, "row_count": 10},
    ]
    session.execute.return_value = result
    with patch("backend.zara_workspace._load_catalog", return_value=_catalog()):
        payload = query_visualization(session, request)

    statement = str(session.execute.call_args.args[0])
    params = session.execute.call_args.args[1]
    assert "WITH workflow_output" in statement
    assert 'GROUP BY "status"' in statement
    assert "Atlas" not in statement
    assert "%Atlas%" in params.values()
    assert payload["data"] == [
        {"label": "In Progress", "value": 7.0},
        {"label": "Blocked", "value": 3.0},
    ]
    assert payload["row_count"] == 10
