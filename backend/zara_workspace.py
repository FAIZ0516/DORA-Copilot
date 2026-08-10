"""Read-only workflow execution and visualization support for Zara."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session


class ZaraWorkspaceError(ValueError):
    """A user-supplied workflow cannot be executed safely."""


class WorkflowNode(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["dataset", "filter", "select", "calculate", "group", "join", "output"]
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)


class WorkflowDefinition(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    nodes: list[WorkflowNode] = Field(min_length=1, max_length=30)
    edges: list[WorkflowEdge] = Field(default_factory=list, max_length=60)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Workflow name cannot be blank")
        return cleaned


class WorkflowRunRequest(BaseModel):
    workflow: WorkflowDefinition
    limit: int = Field(default=100, ge=1, le=100)


class ChartFilter(BaseModel):
    column: str = Field(min_length=1, max_length=80)
    operator: Literal["equals", "not_equals", "contains", "in"]
    value: Any


class VisualizationQueryRequest(BaseModel):
    workflow: WorkflowDefinition
    group_by: str | None = Field(default=None, max_length=80)
    value: str | None = Field(default=None, max_length=80)
    calculation: Literal["count", "sum", "average", "minimum", "maximum", "percentage"]
    filters: list[ChartFilter] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=50, ge=1, le=50)


class VisualizationRecommendRequest(BaseModel):
    workflow: WorkflowDefinition


@dataclass(frozen=True)
class ColumnMetadata:
    name: str
    data_type: str
    nullable: bool

    @property
    def numeric(self) -> bool:
        return bool(
            re.search(
                r"smallint|integer|bigint|decimal|numeric|real|double precision|money",
                self.data_type,
                re.IGNORECASE,
            )
        )

    @property
    def date_like(self) -> bool:
        return bool(re.search(r"date|time", self.data_type, re.IGNORECASE))


@dataclass(frozen=True)
class DatasetMetadata:
    id: str
    schema_name: str
    table_name: str
    relation_type: str
    approximate_rows: int | None
    columns: tuple[ColumnMetadata, ...]


@dataclass(frozen=True)
class CompiledWorkflow:
    sql: str
    params: dict[str, Any]
    columns: tuple[ColumnMetadata, ...]


# Only governed analytical sources are exposed. Development, backup, excluded-issue,
# temporary, and writable assistant objects are deliberately absent.
APPROVED_OBJECTS = frozenset(
    {
        "tbl_gdt_dte_jira_issues",
        "tbl_gdt_dte_release_info",
        "tbl_gdt_dte_releases",
        "vw_gdt_dte_release_frequency",
        "vw_gdt_dte_release_success",
        "mvw_gdt_dte_jira_fixversions",
        "mvw_gdt_dte_jira_fuslist",
        "mvw_gdt_dte_jira_issuelinks",
        "mvw_gdt_dte_jira_labels",
        "mvw_gdt_dte_jira_sprints",
        "mvw_gdt_dte_jira_subtasks",
    }
)
APPROVED_SCHEMAS = frozenset({"enp", "public"})
SENSITIVE_COLUMNS = frozenset(
    {"summary", "reporter", "assignee", "root_cause", "how_to_fix"}
)
UNSUPPORTED_DATA_TYPES = re.compile(r"\b(jsonb?|xml|bytea)\b|\[\]", re.IGNORECASE)

_OBJECT_LIST = ", ".join(f"'{name}'" for name in sorted(APPROVED_OBJECTS))
_OBJECTS_SQL = f"""
    SELECT
        namespace.nspname AS schema_name,
        relation.relname AS table_name,
        CASE relation.relkind
            WHEN 'r' THEN 'table'
            WHEN 'p' THEN 'table'
            WHEN 'v' THEN 'view'
            WHEN 'm' THEN 'materialized_view'
        END AS relation_type,
        CASE WHEN relation.reltuples < 0 THEN NULL
             ELSE relation.reltuples::bigint END AS approximate_rows
    FROM pg_catalog.pg_class AS relation
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname IN ('enp', 'public')
      AND relation.relname IN ({_OBJECT_LIST})
      AND relation.relkind IN ('r', 'p', 'v', 'm')
    ORDER BY CASE namespace.nspname WHEN 'enp' THEN 0 ELSE 1 END,
             relation.relname
"""
_COLUMNS_SQL = f"""
    SELECT
        namespace.nspname AS schema_name,
        relation.relname AS table_name,
        attribute.attname AS column_name,
        pg_catalog.format_type(attribute.atttypid, attribute.atttypmod) AS data_type,
        NOT attribute.attnotnull AS nullable,
        attribute.attnum AS ordinal_position
    FROM pg_catalog.pg_attribute AS attribute
    JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname IN ('enp', 'public')
      AND relation.relname IN ({_OBJECT_LIST})
      AND relation.relkind IN ('r', 'p', 'v', 'm')
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped
    ORDER BY CASE namespace.nspname WHEN 'enp' THEN 0 ELSE 1 END,
             relation.relname,
             attribute.attnum
"""


def _quote(name: str) -> str:
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


def _column_map(columns: tuple[ColumnMetadata, ...]) -> dict[str, ColumnMetadata]:
    return {column.name: column for column in columns}


def _display_name(table_name: str) -> str:
    special = {
        "tbl_gdt_dte_jira_issues": "Jira Issues",
        "tbl_gdt_dte_release_info": "Release Information",
        "tbl_gdt_dte_releases": "Releases",
        "vw_gdt_dte_release_frequency": "Release Frequency",
        "vw_gdt_dte_release_success": "Release Success",
        "mvw_gdt_dte_jira_fixversions": "Jira Fix Versions",
        "mvw_gdt_dte_jira_fuslist": "Jira Feature and Story List",
        "mvw_gdt_dte_jira_issuelinks": "Jira Issue Links",
        "mvw_gdt_dte_jira_labels": "Jira Labels",
        "mvw_gdt_dte_jira_sprints": "Jira Sprints",
        "mvw_gdt_dte_jira_subtasks": "Jira Subtasks",
    }
    return special.get(table_name, table_name.replace("_", " ").title())


def _load_catalog(session: Session) -> dict[str, DatasetMetadata]:
    objects = session.execute(text(_OBJECTS_SQL)).mappings().all()
    column_rows = session.execute(text(_COLUMNS_SQL)).mappings().all()
    columns_by_object: dict[tuple[str, str], list[ColumnMetadata]] = {}
    for row in column_rows:
        name = str(row["column_name"])
        data_type = str(row["data_type"])
        if name.lower() in SENSITIVE_COLUMNS or UNSUPPORTED_DATA_TYPES.search(data_type):
            continue
        key = (str(row["schema_name"]), str(row["table_name"]))
        columns_by_object.setdefault(key, []).append(
            ColumnMetadata(
                name=name,
                data_type=data_type,
                nullable=bool(row["nullable"]),
            )
        )

    catalog: dict[str, DatasetMetadata] = {}
    for row in objects:
        schema_name = str(row["schema_name"])
        table_name = str(row["table_name"])
        if schema_name not in APPROVED_SCHEMAS or table_name not in APPROVED_OBJECTS:
            continue
        columns = tuple(columns_by_object.get((schema_name, table_name), ()))
        if not columns:
            continue
        dataset_id = f"{schema_name}.{table_name}"
        approximate = row["approximate_rows"]
        catalog[dataset_id] = DatasetMetadata(
            id=dataset_id,
            schema_name=schema_name,
            table_name=table_name,
            relation_type=str(row["relation_type"]),
            approximate_rows=int(approximate) if approximate is not None else None,
            columns=columns,
        )
    return catalog


def _dataset(catalog: dict[str, DatasetMetadata], dataset_id: Any) -> DatasetMetadata:
    found = catalog.get(str(dataset_id))
    if found is None:
        raise ZaraWorkspaceError("The selected dataset is not approved or is unavailable.")
    return found


def _dataset_summary(dataset: DatasetMetadata) -> dict[str, Any]:
    relation = dataset.relation_type.replace("_", " ")
    return {
        "id": dataset.id,
        "name": _display_name(dataset.table_name),
        "description": f"Approved read-only DoraDB {relation}.",
        "schema_name": dataset.schema_name,
        "table_name": dataset.table_name,
        "relation_type": dataset.relation_type,
        "column_count": len(dataset.columns),
        "approximate_rows": dataset.approximate_rows,
    }


def list_datasets(session: Session) -> list[dict[str, Any]]:
    return [_dataset_summary(item) for item in _load_catalog(session).values()]


def get_dataset_schema(session: Session, dataset_id: str) -> dict[str, Any]:
    dataset = _dataset(_load_catalog(session), dataset_id)
    return {
        "dataset": _dataset_summary(dataset),
        "columns": [
            {
                "name": column.name,
                "label": column.name.replace("_", " ").title(),
                "data_type": column.data_type,
                "nullable": column.nullable,
                "numeric": column.numeric,
                "date_like": column.date_like,
            }
            for column in dataset.columns
        ],
    }


def get_dataset_values(
    session: Session, dataset_id: str, column_name: str
) -> dict[str, list[Any]]:
    dataset = _dataset(_load_catalog(session), dataset_id)
    if column_name not in _column_map(dataset.columns):
        raise ZaraWorkspaceError("The selected field is not available in this dataset.")
    statement = f"""
        SELECT DISTINCT CAST({_quote(column_name)} AS text) AS value
        FROM {_quote(dataset.schema_name)}.{_quote(dataset.table_name)}
        WHERE {_quote(column_name)} IS NOT NULL
        ORDER BY value
        LIMIT 50
    """
    rows = session.execute(text(statement)).mappings().all()
    return {"values": [row["value"] for row in rows]}


class _Compiler:
    def __init__(
        self, workflow: WorkflowDefinition, catalog: dict[str, DatasetMetadata]
    ) -> None:
        self.workflow = workflow
        self.catalog = catalog
        self.nodes = {node.id: node for node in workflow.nodes}
        if len(self.nodes) != len(workflow.nodes):
            raise ZaraWorkspaceError("Workflow node IDs must be unique.")
        self.parents: dict[str, str] = {}
        for edge in workflow.edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                raise ZaraWorkspaceError("A workflow connection references a missing step.")
            if edge.target in self.parents:
                raise ZaraWorkspaceError("Each workflow step can have only one incoming connection.")
            self.parents[edge.target] = edge.source
        self.params: dict[str, Any] = {}
        self.cache: dict[str, CompiledWorkflow] = {}
        self.visiting: set[str] = set()

    def parameter(self, value: Any) -> str:
        if isinstance(value, (dict, list, tuple, set)):
            raise ZaraWorkspaceError("Filter values must be scalar values.")
        name = f"zara_value_{len(self.params)}"
        self.params[name] = value
        return f":{name}"

    def compile(self) -> CompiledWorkflow:
        outputs = [node for node in self.workflow.nodes if node.type == "output"]
        if len(outputs) != 1:
            raise ZaraWorkspaceError("A workflow must contain exactly one output step.")
        result = self.node(outputs[0].id)
        return CompiledWorkflow(result.sql, dict(self.params), result.columns)

    def node(self, node_id: str) -> CompiledWorkflow:
        if node_id in self.cache:
            return self.cache[node_id]
        if node_id in self.visiting:
            raise ZaraWorkspaceError("Workflow connections cannot contain a cycle.")
        self.visiting.add(node_id)
        node = self.nodes[node_id]

        if node.type == "dataset":
            if node_id in self.parents:
                raise ZaraWorkspaceError("A dataset step cannot have an incoming connection.")
            dataset = _dataset(self.catalog, node.config.get("dataset"))
            projection = ", ".join(
                f"{_quote(column.name)} AS {_quote(column.name)}"
                for column in dataset.columns
            )
            result = CompiledWorkflow(
                f"SELECT {projection} FROM "
                f"{_quote(dataset.schema_name)}.{_quote(dataset.table_name)}",
                self.params,
                dataset.columns,
            )
        else:
            parent_id = self.parents.get(node_id)
            if parent_id is None:
                raise ZaraWorkspaceError(f"The {node.type} step must be connected to an input.")
            incoming = self.node(parent_id)
            result = self._operation(node, incoming)

        self.visiting.remove(node_id)
        self.cache[node_id] = result
        return result

    def _operation(
        self, node: WorkflowNode, incoming: CompiledWorkflow
    ) -> CompiledWorkflow:
        if node.type == "output":
            return incoming
        if node.type == "calculate":
            raise ZaraWorkspaceError("Calculate steps are not enabled yet.")
        if node.type == "filter":
            return self._filter(node, incoming)
        if node.type == "select":
            return self._select(node, incoming)
        if node.type == "group":
            return self._group(node, incoming)
        if node.type == "join":
            return self._join(node, incoming)
        raise ZaraWorkspaceError(f"Unsupported workflow step: {node.type}")

    def _condition(
        self, rule: dict[str, Any], columns: dict[str, ColumnMetadata]
    ) -> str:
        column_name = str(rule.get("column") or "")
        if column_name not in columns:
            raise ZaraWorkspaceError(f"Filter field '{column_name}' is unavailable.")
        column = _quote(column_name)
        operator = str(rule.get("operator") or "")
        if operator == "is_empty":
            return f"({column} IS NULL OR CAST({column} AS text) = '')"
        if operator == "is_not_empty":
            return f"({column} IS NOT NULL AND CAST({column} AS text) <> '')"
        value = self.parameter(rule.get("value"))
        if operator == "equals":
            return f"CAST({column} AS text) = CAST({value} AS text)"
        if operator == "not_equals":
            return f"CAST({column} AS text) IS DISTINCT FROM CAST({value} AS text)"
        if operator == "contains":
            self.params[value[1:]] = f"%{self.params[value[1:]]}%"
            return f"CAST({column} AS text) ILIKE {value}"
        if operator == "not_contains":
            self.params[value[1:]] = f"%{self.params[value[1:]]}%"
            return f"CAST({column} AS text) NOT ILIKE {value}"
        if operator == "starts_with":
            self.params[value[1:]] = f"{self.params[value[1:]]}%"
            return f"CAST({column} AS text) ILIKE {value}"
        if operator == "ends_with":
            self.params[value[1:]] = f"%{self.params[value[1:]]}"
            return f"CAST({column} AS text) ILIKE {value}"
        comparisons = {
            "greater_than": ">",
            "greater_or_equal": ">=",
            "greater_than_or_equal": ">=",
            "less_than": "<",
            "less_or_equal": "<=",
            "less_than_or_equal": "<=",
            "before": "<",
            "after": ">",
        }
        if operator in comparisons:
            return f"{column} {comparisons[operator]} {value}"
        if operator == "between":
            value_to = self.parameter(rule.get("value_to"))
            return f"{column} BETWEEN {value} AND {value_to}"
        raise ZaraWorkspaceError(f"Unsupported filter operator: {operator}")

    def _filter(
        self, node: WorkflowNode, incoming: CompiledWorkflow
    ) -> CompiledWorkflow:
        raw_rules = node.config.get("rules")
        rules = raw_rules if isinstance(raw_rules, list) else [node.config]
        if not rules or any(not isinstance(rule, dict) for rule in rules):
            raise ZaraWorkspaceError("A filter step needs at least one valid condition.")
        conditions = [
            self._condition(rule, _column_map(incoming.columns)) for rule in rules
        ]
        connector = " OR " if node.config.get("match") == "any" else " AND "
        return CompiledWorkflow(
            f"SELECT * FROM ({incoming.sql}) AS source_rows WHERE "
            f"({connector.join(conditions)})",
            self.params,
            incoming.columns,
        )

    def _select(
        self, node: WorkflowNode, incoming: CompiledWorkflow
    ) -> CompiledWorkflow:
        selected = node.config.get("columns")
        if not isinstance(selected, list) or not selected:
            raise ZaraWorkspaceError("Select Columns needs at least one field.")
        available = _column_map(incoming.columns)
        names = [str(name) for name in selected]
        if len(names) != len(set(names)) or any(name not in available for name in names):
            raise ZaraWorkspaceError("Select Columns contains an unavailable field.")
        columns = tuple(available[name] for name in names)
        projection = ", ".join(_quote(name) for name in names)
        return CompiledWorkflow(
            f"SELECT {projection} FROM ({incoming.sql}) AS source_rows",
            self.params,
            columns,
        )

    def _group(
        self, node: WorkflowNode, incoming: CompiledWorkflow
    ) -> CompiledWorkflow:
        available = _column_map(incoming.columns)
        group_by = str(node.config.get("group_by") or "")
        if group_by not in available:
            raise ZaraWorkspaceError("The selected grouping field is unavailable.")
        calculation = str(node.config.get("calculation") or "count")
        value_name = str(node.config.get("value") or "")
        result_name = str(
            node.config.get("result_name")
            or ("issue_count" if calculation == "count" else f"{calculation}_{value_name}")
        ).strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,62}", result_name):
            raise ZaraWorkspaceError("The result label contains unsupported characters.")
        if calculation == "count":
            aggregate = "COUNT(*)::bigint"
        else:
            if value_name not in available:
                raise ZaraWorkspaceError("The selected summary field is unavailable.")
            value_column = _quote(value_name)
            if calculation == "count_distinct":
                aggregate = f"COUNT(DISTINCT {value_column})::bigint"
            elif calculation in {"sum", "average", "minimum", "maximum"}:
                if not available[value_name].numeric:
                    raise ZaraWorkspaceError("This summary requires a numeric field.")
                function = {
                    "sum": "SUM",
                    "average": "AVG",
                    "minimum": "MIN",
                    "maximum": "MAX",
                }[calculation]
                aggregate = f"{function}({value_column})"
            else:
                raise ZaraWorkspaceError(f"Unsupported summary calculation: {calculation}")
        group_column = _quote(group_by)
        columns = (
            available[group_by],
            ColumnMetadata(result_name, "numeric", False),
        )
        return CompiledWorkflow(
            f"SELECT {group_column}, {aggregate} AS {_quote(result_name)} "
            f"FROM ({incoming.sql}) AS source_rows GROUP BY {group_column}",
            self.params,
            columns,
        )

    def _join(
        self, node: WorkflowNode, incoming: CompiledWorkflow
    ) -> CompiledWorkflow:
        right = _dataset(self.catalog, node.config.get("dataset"))
        left_name = str(node.config.get("left_column") or "")
        right_name = str(node.config.get("right_column") or "")
        left_columns = _column_map(incoming.columns)
        right_columns = _column_map(right.columns)
        if left_name not in left_columns or right_name not in right_columns:
            raise ZaraWorkspaceError("The join fields are unavailable.")
        join_type = "INNER" if node.config.get("join_type") == "inner" else "LEFT"
        output_columns = list(incoming.columns)
        used = {column.name for column in output_columns}
        projections = [
            f"left_rows.{_quote(column.name)} AS {_quote(column.name)}"
            for column in incoming.columns
        ]
        for column in right.columns:
            candidate = column.name if column.name not in used else f"joined_{column.name}"
            suffix = 2
            while candidate in used:
                candidate = f"joined_{column.name}_{suffix}"
                suffix += 1
            used.add(candidate)
            projections.append(
                f"right_rows.{_quote(column.name)} AS {_quote(candidate)}"
            )
            output_columns.append(
                ColumnMetadata(candidate, column.data_type, column.nullable)
            )
        qualified = f"{_quote(right.schema_name)}.{_quote(right.table_name)}"
        return CompiledWorkflow(
            f"SELECT {', '.join(projections)} FROM ({incoming.sql}) AS left_rows "
            f"{join_type} JOIN {qualified} AS right_rows ON "
            f"left_rows.{_quote(left_name)} = right_rows.{_quote(right_name)}",
            self.params,
            tuple(output_columns),
        )


def compile_workflow(
    workflow: WorkflowDefinition, catalog: dict[str, DatasetMetadata]
) -> CompiledWorkflow:
    return _Compiler(workflow, catalog).compile()


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, UUID)):
        return value.isoformat() if not isinstance(value, UUID) else str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def run_workflow(session: Session, request: WorkflowRunRequest) -> dict[str, Any]:
    started = perf_counter()
    compiled = compile_workflow(request.workflow, _load_catalog(session))
    params = {**compiled.params, "zara_preview_limit": request.limit + 1}
    statement = (
        f"SELECT * FROM ({compiled.sql}) AS zara_output "
        "LIMIT :zara_preview_limit"
    )
    raw_rows = session.execute(text(statement), params).mappings().all()
    truncated = len(raw_rows) > request.limit
    rows = raw_rows[: request.limit]
    return {
        "columns": [column.name for column in compiled.columns],
        "rows": [
            {key: _json_value(value) for key, value in row.items()} for row in rows
        ],
        "row_count": len(rows),
        "preview_limit": request.limit,
        "truncated": truncated,
        "execution_time_ms": max(1, round((perf_counter() - started) * 1000)),
    }


def _chart_filter_sql(
    filters: list[ChartFilter], columns: dict[str, ColumnMetadata], params: dict[str, Any]
) -> str:
    conditions: list[str] = []
    for chart_filter in filters:
        if chart_filter.column not in columns:
            raise ZaraWorkspaceError(
                f"Chart filter field '{chart_filter.column}' is unavailable."
            )
        column = _quote(chart_filter.column)
        if chart_filter.operator == "in":
            values = (
                list(chart_filter.value)
                if isinstance(chart_filter.value, (list, tuple, set))
                else [chart_filter.value]
            )
            if not values or len(values) > 50:
                raise ZaraWorkspaceError("Chart 'in' filters need between 1 and 50 values.")
            placeholders: list[str] = []
            for value in values:
                if isinstance(value, (dict, list, tuple, set)):
                    raise ZaraWorkspaceError("Chart filter values must be scalar values.")
                name = f"chart_value_{len(params)}"
                params[name] = value
                placeholders.append(f":{name}")
            conditions.append(f"{column} IN ({', '.join(placeholders)})")
            continue
        if isinstance(chart_filter.value, (dict, list, tuple, set)):
            raise ZaraWorkspaceError("Chart filter values must be scalar values.")
        name = f"chart_value_{len(params)}"
        params[name] = chart_filter.value
        placeholder = f":{name}"
        if chart_filter.operator == "equals":
            conditions.append(
                f"CAST({column} AS text) = CAST({placeholder} AS text)"
            )
        elif chart_filter.operator == "not_equals":
            conditions.append(
                f"CAST({column} AS text) IS DISTINCT FROM CAST({placeholder} AS text)"
            )
        else:
            params[name] = f"%{chart_filter.value}%"
            conditions.append(f"CAST({column} AS text) ILIKE {placeholder}")
    return f"WHERE {' AND '.join(conditions)}" if conditions else ""


def query_visualization(
    session: Session, request: VisualizationQueryRequest
) -> dict[str, Any]:
    started = perf_counter()
    compiled = compile_workflow(request.workflow, _load_catalog(session))
    columns = _column_map(compiled.columns)
    if request.group_by is not None and request.group_by not in columns:
        raise ZaraWorkspaceError("The selected chart grouping field is unavailable.")
    if request.value is not None and request.value not in columns:
        raise ZaraWorkspaceError("The selected chart value field is unavailable.")
    if request.calculation in {"sum", "average", "minimum", "maximum"}:
        if request.value is None or not columns[request.value].numeric:
            raise ZaraWorkspaceError("This chart calculation requires a numeric field.")

    params = dict(compiled.params)
    where_clause = _chart_filter_sql(request.filters, columns, params)
    params["zara_chart_limit"] = request.limit
    if request.calculation == "count":
        aggregate = "COUNT(*)::double precision"
    elif request.calculation == "percentage":
        aggregate = (
            "COALESCE(100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM filtered), 0), 0)"
        )
    else:
        function = {
            "sum": "SUM",
            "average": "AVG",
            "minimum": "MIN",
            "maximum": "MAX",
        }[request.calculation]
        aggregate = f"COALESCE({function}({_quote(request.value or '')}), 0)::double precision"

    if request.group_by:
        group = _quote(request.group_by)
        select_sql = (
            f"SELECT COALESCE(CAST({group} AS text), 'Not set') AS label, "
            f"{aggregate} AS value, "
            "(SELECT COUNT(*) FROM filtered) AS row_count "
            f"FROM filtered GROUP BY {group} "
            "ORDER BY value DESC NULLS LAST, label LIMIT :zara_chart_limit"
        )
    else:
        select_sql = (
            f"SELECT 'All records' AS label, {aggregate} AS value, "
            "COUNT(*) AS row_count FROM filtered"
        )
    statement = f"""
        WITH workflow_output AS ({compiled.sql}),
        filtered AS (SELECT * FROM workflow_output {where_clause})
        {select_sql}
    """
    rows = session.execute(text(statement), params).mappings().all()
    return {
        "data": [
            {"label": str(row["label"]), "value": float(row["value"] or 0)}
            for row in rows
        ],
        "row_count": int(rows[0]["row_count"]) if rows else 0,
        "execution_time_ms": max(1, round((perf_counter() - started) * 1000)),
    }


def recommend_visualizations(
    session: Session, request: VisualizationRecommendRequest
) -> dict[str, list[dict[str, Any]]]:
    compiled = compile_workflow(request.workflow, _load_catalog(session))
    columns = list(compiled.columns)
    charts: list[dict[str, Any]] = [
        {
            "title": "Total Prepared Records",
            "subtitle": "Rows in the current workflow output",
            "type": "kpi",
            "group_by": None,
            "value": None,
            "calculation": "count",
            "filters": [],
        }
    ]
    preferred_tokens = ("status", "category", "type", "squad", "priority", "year", "release")
    categorical = [
        column
        for column in columns
        if not column.numeric
        and not column.date_like
        and not re.search(r"(^id$|_id$|^key$|_key$)", column.name, re.IGNORECASE)
    ]
    categorical.sort(
        key=lambda column: next(
            (index for index, token in enumerate(preferred_tokens) if token in column.name.lower()),
            len(preferred_tokens),
        )
    )
    for index, column in enumerate(categorical[:2]):
        label = column.name.replace("_", " ").title()
        charts.append(
            {
                "title": f"Records by {label}",
                "subtitle": "Grouped from the prepared workflow output",
                "type": "bar" if index == 0 else "donut",
                "group_by": column.name,
                "value": None,
                "calculation": "count",
                "filters": [],
            }
        )
    date_column = next((column for column in columns if column.date_like), None)
    if date_column and len(charts) < 4:
        label = date_column.name.replace("_", " ").title()
        charts.append(
            {
                "title": f"Records by {label}",
                "subtitle": "Timeline from the prepared workflow output",
                "type": "line",
                "group_by": date_column.name,
                "value": None,
                "calculation": "count",
                "filters": [],
            }
        )
    numeric_column = next((column for column in columns if column.numeric), None)
    if numeric_column and len(charts) < 4:
        label = numeric_column.name.replace("_", " ").title()
        charts.append(
            {
                "title": f"Total {label}",
                "subtitle": "Numeric total from the prepared workflow output",
                "type": "bar" if categorical else "kpi",
                "group_by": categorical[0].name if categorical else None,
                "value": numeric_column.name,
                "calculation": "sum",
                "filters": [],
            }
        )
    return {"charts": charts[:4]}
