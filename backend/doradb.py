"""Read-only DoraDB connection and approved parameterized query execution."""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .doradb_catalog import (
    ALLOWED_FILTERS,
    APPROVED_QUERY_IDS,
    LARGE_QUERY_IDS,
    LARGE_QUERY_REQUIRED_FILTERS,
    QUERY_CATALOGUE,
)


class DoraDbConfigurationError(RuntimeError):
    """The real database mode is selected but credentials are missing."""


class DoraDbQueryRejected(ValueError):
    """A query ID, filter, or requested result size violated the allowlist."""


_BASE_QUERIES = {
    "database_schema_objects": """
        SELECT
            table_schema,
            table_name,
            CASE table_type
                WHEN 'BASE TABLE' THEN 'table'
                ELSE LOWER(table_type)
            END AS object_type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    """,
    "database_table_presence": """
        SELECT
            table_schema,
            table_name,
            CASE table_type
                WHEN 'BASE TABLE' THEN 'table'
                ELSE LOWER(table_type)
            END AS object_type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    """,
    "database_columns": """
        SELECT
            table_schema,
            table_name,
            column_name,
            data_type,
            is_nullable,
            ordinal_position
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    """,
    "database_metric_columns": """
        SELECT
            table_schema,
            table_name,
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND (
              LOWER(column_name) LIKE '%lead%'
              OR LOWER(column_name) LIKE '%cycle%'
              OR LOWER(column_name) = 'ltc'
              OR LOWER(column_name) IN ('created', 'resolved')
          )
    """,
    "database_squad_sources": """
        SELECT
            table_schema,
            table_name,
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND LOWER(column_name) IN (
              'dcpsquad', 'squad', 'squad_id', 'squad_name', 'team', 'team_name'
          )
    """,
    "jira_distinct_squads": """
        SELECT
            BTRIM(j.dcpsquad) AS dcpsquad,
            (
                SELECT COUNT(*)
                FROM public.tbl_gdt_dte_jira_issues AS missing
                WHERE missing.project_key = :project_key
                  AND (
                      missing.dcpsquad IS NULL
                      OR BTRIM(missing.dcpsquad) = ''
                  )
            ) AS missing_squad_rows
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
          AND j.dcpsquad IS NOT NULL
          AND BTRIM(j.dcpsquad) <> ''
        GROUP BY BTRIM(j.dcpsquad)
    """,
    "jira_bug_counts_by_squad": """
        SELECT
            BTRIM(j.dcpsquad) AS dcpsquad,
            COUNT(*) AS bug_count
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
          AND LOWER(COALESCE(j.issuetype, '')) = 'bug'
          AND j.dcpsquad IS NOT NULL
          AND BTRIM(j.dcpsquad) <> ''
        GROUP BY BTRIM(j.dcpsquad)
    """,
    "jira_issue_counts_by_status": """
        SELECT
            j.issuetype,
            j.status,
            j.status_category,
            COUNT(*) AS issue_count
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
        GROUP BY j.issuetype, j.status, j.status_category
    """,
    "jira_unresolved_older_than_days": """
        SELECT
            j.status,
            j.status_category,
            COUNT(*) AS issue_count,
            MIN(j.created) AS oldest_created
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
          AND j.resolved IS NULL
          AND j.created < CURRENT_TIMESTAMP - (:age_days * INTERVAL '1 day')
        GROUP BY j.status, j.status_category
    """,
    "jira_backlog_by_status": """
        SELECT
            j.status,
            j.status_category,
            COUNT(*) AS issue_count
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
          AND j.resolved IS NULL
          AND COALESCE(j.status_category, '') <> 'Done'
        GROUP BY j.status, j.status_category
    """,
    "jira_bug_resolution_trend": """
        WITH created_counts AS (
            SELECT
                DATE_TRUNC('month', created)::date AS month,
                COUNT(*) AS created_bug_count
            FROM public.tbl_gdt_dte_jira_issues
            WHERE project_key = :project_key
              AND LOWER(COALESCE(issuetype, '')) = 'bug'
            GROUP BY DATE_TRUNC('month', created)::date
        ),
        resolved_counts AS (
            SELECT
                DATE_TRUNC('month', resolved)::date AS month,
                COUNT(*) AS resolved_bug_count
            FROM public.tbl_gdt_dte_jira_issues
            WHERE project_key = :project_key
              AND LOWER(COALESCE(issuetype, '')) = 'bug'
              AND resolved IS NOT NULL
              AND resolved >= created
            GROUP BY DATE_TRUNC('month', resolved)::date
        )
        SELECT
            COALESCE(c.month, r.month) AS month,
            COALESCE(c.created_bug_count, 0) AS created_bug_count,
            COALESCE(r.resolved_bug_count, 0) AS resolved_bug_count
        FROM created_counts AS c
        FULL OUTER JOIN resolved_counts AS r USING (month)
    """,
    "jira_dashboard_kpis": """
        SELECT
            COUNT(*) AS total_issues,
            COUNT(*) FILTER (
                WHERE j.resolved IS NULL AND j.status_category <> 'Done'
            ) AS open_work_count,
            COUNT(*) FILTER (WHERE j.status = 'IMPEDED') AS impeded_issues,
            COUNT(*) FILTER (
                WHERE j.dcpsquad IS NULL OR BTRIM(j.dcpsquad) = ''
            ) AS missing_squad_count,
            ROUND(
                100.0 * COUNT(*) FILTER (
                    WHERE j.dcpsquad IS NULL OR BTRIM(j.dcpsquad) = ''
                ) / NULLIF(COUNT(*), 0),
                2
            ) AS missing_squad_pct
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
    """,
    "jira_dashboard_status_categories": """
        SELECT
            COALESCE(NULLIF(BTRIM(j.status_category), ''), 'Unknown') AS status_category,
            COUNT(*) AS issue_count
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
        GROUP BY COALESCE(NULLIF(BTRIM(j.status_category), ''), 'Unknown')
    """,
    "jira_dashboard_issue_types": """
        SELECT
            COALESCE(NULLIF(BTRIM(j.issuetype), ''), 'Unknown') AS issuetype,
            COUNT(*) AS issue_count
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
        GROUP BY COALESCE(NULLIF(BTRIM(j.issuetype), ''), 'Unknown')
    """,
    "jira_dashboard_open_ageing": """
        SELECT
            CASE
                WHEN j.created IS NULL THEN 'Unknown created date'
                WHEN CURRENT_DATE - j.created::date < 30 THEN 'Less than 30 days'
                WHEN CURRENT_DATE - j.created::date BETWEEN 30 AND 60 THEN '30-60 days'
                WHEN CURRENT_DATE - j.created::date BETWEEN 61 AND 90 THEN '61-90 days'
                ELSE 'More than 90 days'
            END AS ageing_bucket,
            COUNT(*) AS issue_count,
            CASE
                WHEN j.created IS NULL THEN 5
                WHEN CURRENT_DATE - j.created::date < 30 THEN 1
                WHEN CURRENT_DATE - j.created::date BETWEEN 30 AND 60 THEN 2
                WHEN CURRENT_DATE - j.created::date BETWEEN 61 AND 90 THEN 3
                ELSE 4
            END AS bucket_order
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
          AND j.resolved IS NULL
          AND j.status_category <> 'Done'
        GROUP BY ageing_bucket, bucket_order
    """,
    "jira_dashboard_data_quality": """
        SELECT
            COUNT(*) FILTER (
                WHERE j.dcpsquad IS NULL OR BTRIM(j.dcpsquad) = ''
            ) AS missing_squad_count,
            COUNT(*) FILTER (
                WHERE j.assignee IS NULL OR BTRIM(j.assignee) = ''
            ) AS missing_assignee_count,
            COUNT(*) FILTER (
                WHERE j.status_category = 'Done' AND j.resolved IS NULL
            ) AS done_without_resolved_count,
            COUNT(*) FILTER (
                WHERE j.resolved IS NOT NULL
                  AND j.created IS NOT NULL
                  AND j.resolved < j.created
            ) AS invalid_resolution_interval_count
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
    """,
    "jira_open_work_breakdown": """
        SELECT
            CASE
                WHEN j.created IS NULL THEN 'Unknown created date'
                WHEN CURRENT_DATE - j.created::date < 30 THEN 'Less than 30 days'
                WHEN CURRENT_DATE - j.created::date BETWEEN 30 AND 60 THEN '30-60 days'
                WHEN CURRENT_DATE - j.created::date BETWEEN 61 AND 90 THEN '61-90 days'
                ELSE 'More than 90 days'
            END AS ageing_bucket,
            COALESCE(NULLIF(BTRIM(j.issuetype), ''), 'Unknown') AS issuetype,
            COALESCE(NULLIF(BTRIM(j.priority), ''), 'Unknown') AS priority,
            COALESCE(NULLIF(BTRIM(j.status_category), ''), 'Unknown') AS status_category,
            CASE
                WHEN j.dcpsquad IS NULL OR BTRIM(j.dcpsquad) = '' THEN 'Missing squad'
                ELSE 'Squad populated'
            END AS squad_coverage,
            COUNT(*) AS issue_count
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
          AND j.resolved IS NULL
          AND j.status_category <> 'Done'
        GROUP BY ageing_bucket, issuetype, priority, status_category, squad_coverage
    """,
    "jira_impeded_breakdown": """
        SELECT
            CASE
                WHEN j.created IS NULL THEN 'Unknown created date'
                WHEN CURRENT_DATE - j.created::date < 30 THEN 'Less than 30 days'
                WHEN CURRENT_DATE - j.created::date BETWEEN 30 AND 60 THEN '30-60 days'
                WHEN CURRENT_DATE - j.created::date BETWEEN 61 AND 90 THEN '61-90 days'
                ELSE 'More than 90 days'
            END AS ageing_bucket,
            COALESCE(NULLIF(BTRIM(j.issuetype), ''), 'Unknown') AS issuetype,
            COALESCE(NULLIF(BTRIM(j.priority), ''), 'Unknown') AS priority,
            CASE
                WHEN j.dcpsquad IS NULL OR BTRIM(j.dcpsquad) = '' THEN 'Missing squad'
                ELSE 'Squad populated'
            END AS squad_coverage,
            COUNT(*) AS issue_count
        FROM public.tbl_gdt_dte_jira_issues AS j
        WHERE j.project_key = :project_key
          AND j.status = 'IMPEDED'
        GROUP BY ageing_bucket, issuetype, priority, squad_coverage
    """,
    "dora_metrics_by_year": """
        WITH dora AS (
            SELECT
                release_year::integer AS release_year,
                COUNT(*) AS release_count,
                ROUND(AVG(major_release_freq), 2) AS release_frequency_months,
                ROUND(AVG(ltc), 2) AS lead_time_for_change_months,
                ROUND(AVG(overall_actual_diff::numeric / 30.0), 2)
                    AS delivery_cycle_time_months
            FROM public.vw_gdt_dte_release_frequency
            GROUP BY release_year
        ),
        failure AS (
            SELECT
                EXTRACT(YEAR FROM release_date)::integer AS release_year,
                ROUND(AVG(outcome_rating) * 100, 2) AS change_failure_rate_pct
            FROM public.tbl_gdt_dte_release_info
            WHERE release_category = 1
            GROUP BY EXTRACT(YEAR FROM release_date)
        ),
        features AS (
            SELECT
                release_year,
                COUNT(*) FILTER (WHERE LOWER(issuetype) = 'user story')
                    AS user_story_count,
                COUNT(*) FILTER (WHERE LOWER(issuetype) = 'feature')
                    AS feature_reference_count,
                COUNT(DISTINCT release_name) AS feature_reference_release_count
            FROM public.mvw_gdt_dte_jira_fuslist
            WHERE hide_flag IS NOT TRUE
            GROUP BY release_year
        )
        SELECT
            d.release_year,
            d.release_count,
            d.release_frequency_months,
            f.change_failure_rate_pct,
            d.lead_time_for_change_months,
            d.delivery_cycle_time_months,
            x.user_story_count,
            x.feature_reference_count,
            x.feature_reference_release_count
        FROM dora AS d
        LEFT JOIN failure AS f USING (release_year)
        LEFT JOIN features AS x USING (release_year)
    """,
    "dora_metrics_by_squad": """
        WITH squad_issue_versions AS (
            SELECT
                j.key AS jira_key,
                j.issuetype,
                jsonb_array_elements_text(
                    COALESCE(
                        j.fixversions::jsonb -> 'fixversions',
                        '[]'::jsonb
                    )
                ) AS fixversion
            FROM public.tbl_gdt_dte_jira_issues AS j
            WHERE j.project_key = :project_key
              AND UPPER(COALESCE(j.dcpsquad, '')) = UPPER(:dcpsquad)
        ),
        squad_release_versions AS (
            SELECT DISTINCT fixversion
            FROM squad_issue_versions
            WHERE fixversion <> ''
        ),
        dora AS (
            SELECT
                f.release_year::integer AS release_year,
                COUNT(*) AS release_count,
                ROUND(AVG(f.major_release_freq), 2)
                    AS release_frequency_months,
                ROUND(AVG(f.outcome_rating) * 100, 2)
                    AS change_failure_rate_pct,
                ROUND(AVG(f.ltc), 2) AS lead_time_for_change_months,
                ROUND(AVG(f.overall_actual_diff::numeric / 30.0), 2)
                    AS delivery_cycle_time_months
            FROM public.vw_gdt_dte_release_frequency AS f
            JOIN squad_release_versions AS squad
              ON squad.fixversion = f.fixversion
            WHERE f.release_category = 1
            GROUP BY f.release_year
        ),
        issue_counts AS (
            SELECT
                EXTRACT(YEAR FROM r.release_date)::integer AS release_year,
                COUNT(*) FILTER (
                    WHERE LOWER(s.issuetype) = 'user story'
                ) AS user_story_count,
                COUNT(*) FILTER (
                    WHERE LOWER(s.issuetype) = 'feature'
                ) AS feature_reference_count,
                COUNT(DISTINCT s.fixversion)
                    AS feature_reference_release_count
            FROM squad_issue_versions AS s
            JOIN public.tbl_gdt_dte_release_info AS r
              ON r.fixversion = s.fixversion
            WHERE r.release_category = 1
            GROUP BY EXTRACT(YEAR FROM r.release_date)
        )
        SELECT
            UPPER(:dcpsquad) AS dcpsquad,
            d.release_year,
            d.release_count,
            d.release_frequency_months,
            d.change_failure_rate_pct,
            d.lead_time_for_change_months,
            d.delivery_cycle_time_months,
            COALESCE(i.user_story_count, 0) AS user_story_count,
            COALESCE(i.feature_reference_count, 0)
                AS feature_reference_count,
            COALESCE(i.feature_reference_release_count, 0)
                AS feature_reference_release_count
        FROM dora AS d
        LEFT JOIN issue_counts AS i USING (release_year)
    """,
    "dora_metrics_release_detail": """
        SELECT
            COALESCE(i.release_name_sorted, f.fixversion) AS fixversion,
            f.release_category,
            f.release_year::integer AS release_year,
            COALESCE(s.success_rel_freq, 0) AS release_frequency,
            AVG(s.success_rel_freq) OVER (
                PARTITION BY f.release_year ORDER BY f.release_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS avg_release_frequency,
            f.release_date,
            f.outcome_rating,
            SUM(f.outcome_rating) OVER (
                PARTITION BY f.release_year ORDER BY f.release_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cumulative_outcome_rating,
            COUNT(*) OVER (
                PARTITION BY f.release_year ORDER BY f.release_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cumulative_major_release_count,
            SUM(f.outcome_rating) OVER (
                PARTITION BY f.release_year ORDER BY f.release_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) / NULLIF(
                COUNT(*) OVER (
                    PARTITION BY f.release_year ORDER BY f.release_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ),
                0
            ) AS cumulative_change_failure_ratio,
            f.dev_insprint_actual_start,
            f.release_actual_start,
            f.release_actual_end,
            COALESCE(s.delivery_cycle_time, 0) AS delivery_cycle_time,
            f.overall_actual_diff,
            f.ltc,
            AVG(f.ltc) OVER (
                PARTITION BY f.release_year ORDER BY f.release_date
                ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
            ) AS rolling_two_release_avg_ltc
        FROM public.vw_gdt_dte_release_frequency AS f
        LEFT JOIN public.vw_gdt_dte_release_success AS s ON s.r_id = f.r_id
        LEFT JOIN public.tbl_gdt_dte_release_info AS i ON i.r_id = f.r_id
        WHERE f.release_category = 1
    """,
    "feature_vs_release_frequency": """
        SELECT
            f.release_name_sorted AS fixversion,
            f.release_year,
            f.issuetype,
            f.key AS jira_key,
            f.status,
            f.major_flag,
            r.outcome_rating,
            r.release_category,
            r.release_date,
            s.success_rel_freq AS release_frequency_months
        FROM public.mvw_gdt_dte_jira_fuslist AS f
        JOIN public.tbl_gdt_dte_jira_issues AS j ON j.key = f.key
        LEFT JOIN public.vw_gdt_dte_release_frequency AS r
            ON r.fixversion = f.release_name
        LEFT JOIN public.vw_gdt_dte_release_success AS s ON s.r_id = r.r_id
        WHERE f.major_flag IS TRUE AND j.project_key = :project_key
    """,
    "feature_vs_user_story": """
        SELECT
            f.release_year,
            f.release_major,
            f.release_name_sorted AS fixversion,
            f.release_name,
            f.id,
            f.key AS jira_key,
            f.issuetype,
            f.status,
            f.major_flag,
            f.hide_flag,
            r.release_date
        FROM public.mvw_gdt_dte_jira_fuslist AS f
        JOIN public.tbl_gdt_dte_jira_issues AS j ON j.key = f.key
        LEFT JOIN public.tbl_gdt_dte_releases AS r
            ON r.release_name = f.release_name
        WHERE j.project_key = :project_key
    """,
    "story_to_feature_ratio": """
        SELECT
            f.release_year,
            f.release_name_sorted AS fixversion,
            ROUND(
                COUNT(*) FILTER (WHERE f.issuetype = 'User Story')::numeric
                / NULLIF(COUNT(*) FILTER (WHERE f.issuetype = 'Feature'), 0),
                2
            ) AS user_story_to_feature_ratio,
            COUNT(*) FILTER (WHERE f.issuetype = 'User Story') AS user_story_count,
            COUNT(*) FILTER (WHERE f.issuetype = 'Feature') AS feature_count
        FROM public.mvw_gdt_dte_jira_fuslist AS f
        JOIN public.tbl_gdt_dte_jira_issues AS j ON j.key = f.key
        WHERE j.project_key = :project_key
        GROUP BY f.release_year, f.release_name_sorted
    """,
}

_FILTER_COLUMNS = {
    "database_schema_objects": {
        "table_schema": "approved.table_schema",
        "table_name": "approved.table_name",
    },
    "database_table_presence": {
        "table_schema": "approved.table_schema",
        "table_name": "approved.table_name",
    },
    "database_columns": {
        "table_schema": "approved.table_schema",
        "table_name": "approved.table_name",
        "column_search": "approved.column_name",
    },
    "database_metric_columns": {},
    "database_squad_sources": {},
    "jira_distinct_squads": {},
    "jira_bug_counts_by_squad": {},
    "jira_issue_counts_by_status": {
        "issuetype": "approved.issuetype",
        "status": "approved.status",
    },
    "jira_unresolved_older_than_days": {},
    "jira_backlog_by_status": {},
    "jira_bug_resolution_trend": {},
    "jira_dashboard_kpis": {},
    "jira_dashboard_status_categories": {},
    "jira_dashboard_issue_types": {},
    "jira_dashboard_open_ageing": {},
    "jira_dashboard_data_quality": {},
    "jira_open_work_breakdown": {
        "ageing_bucket": "approved.ageing_bucket",
    },
    "jira_impeded_breakdown": {},
    "dora_metrics_by_year": {
        "release_year": "approved.release_year",
    },
    "dora_metrics_by_squad": {
        "release_year": "approved.release_year",
    },
    "dora_metrics_release_detail": {
        "release_year": "approved.release_year",
        "release_date": "approved.release_date",
        "fixversion": "approved.fixversion",
        "release_name": "approved.fixversion",
    },
    "feature_vs_release_frequency": {
        "release_year": "approved.release_year",
        "fixversion": "approved.fixversion",
        "release_name": "approved.fixversion",
        "issuetype": "approved.issuetype",
        "jira_key": "approved.jira_key",
        "status": "approved.status",
    },
    "feature_vs_user_story": {
        "release_year": "approved.release_year",
        "fixversion": "approved.fixversion",
        "release_name": "approved.release_name",
        "issuetype": "approved.issuetype",
        "jira_key": "approved.jira_key",
        "status": "approved.status",
    },
    "story_to_feature_ratio": {
        "release_year": "approved.release_year",
        "fixversion": "approved.fixversion",
        "release_name": "approved.fixversion",
    },
}

_ORDER_BY = {
    "database_schema_objects": "approved.table_schema, approved.table_name",
    "database_table_presence": "approved.table_schema, approved.table_name",
    "database_columns": (
        "approved.table_schema, approved.table_name, approved.ordinal_position"
    ),
    "database_metric_columns": (
        "approved.table_schema, approved.table_name, approved.column_name"
    ),
    "database_squad_sources": (
        "approved.table_schema, approved.table_name, approved.column_name"
    ),
    "jira_distinct_squads": "approved.dcpsquad",
    "jira_bug_counts_by_squad": "approved.bug_count DESC, approved.dcpsquad",
    "jira_issue_counts_by_status": "approved.issue_count DESC, approved.status",
    "jira_unresolved_older_than_days": "approved.issue_count DESC, approved.status",
    "jira_backlog_by_status": "approved.issue_count DESC, approved.status",
    "jira_bug_resolution_trend": "approved.month DESC",
    "jira_dashboard_kpis": "approved.total_issues DESC",
    "jira_dashboard_status_categories": "approved.issue_count DESC, approved.status_category",
    "jira_dashboard_issue_types": "approved.issue_count DESC, approved.issuetype",
    "jira_dashboard_open_ageing": "approved.bucket_order",
    "jira_dashboard_data_quality": "approved.missing_squad_count DESC",
    "jira_open_work_breakdown": "approved.issue_count DESC, approved.ageing_bucket",
    "jira_impeded_breakdown": "approved.issue_count DESC, approved.ageing_bucket",
    "dora_metrics_by_year": "approved.release_year DESC",
    "dora_metrics_by_squad": "approved.release_year DESC",
    "dora_metrics_release_detail": "approved.release_date DESC NULLS LAST",
    "feature_vs_release_frequency": (
        "approved.release_year DESC, approved.fixversion, approved.jira_key"
    ),
    "feature_vs_user_story": (
        "approved.release_year DESC, approved.fixversion DESC, approved.jira_key"
    ),
    "story_to_feature_ratio": "approved.release_year DESC, approved.fixversion",
}


def _engine():
    if not settings.doradb_configured:
        return None
    timeout_ms = settings.doradb_query_timeout_seconds * 1000
    return create_engine(
        settings.doradb_url,
        pool_pre_ping=True,
        connect_args={
            "options": (
                "-c default_transaction_read_only=on "
                f"-c statement_timeout={timeout_ms}"
            )
        },
    )


doradb_engine = _engine()
DoraDbSessionLocal = (
    sessionmaker(bind=doradb_engine, class_=Session, autoflush=False, expire_on_commit=False)
    if doradb_engine is not None
    else None
)


@contextmanager
def doradb_session() -> Iterator[Session]:
    """Yield a real DoraDB session or fail without exposing credentials."""

    if DoraDbSessionLocal is None:
        raise DoraDbConfigurationError(
            "DoraDB credentials are not configured. Add DORADB_USER and "
            "DORADB_PASSWORD to .env."
        )
    session = DoraDbSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def check_doradb(session: Session) -> None:
    """Verify connectivity and read-only transaction state."""

    read_only = session.scalar(text("SHOW transaction_read_only"))
    if str(read_only).lower() != "on":
        raise DoraDbConfigurationError("DoraDB connection is not read-only")
    session.execute(text("SELECT 1"))


def _normalize_filters(query_id: str, raw_filters: dict[str, Any]) -> dict[str, Any]:
    allowed_for_query = set(QUERY_CATALOGUE[query_id]["allowed_filters"])
    normalized: dict[str, Any] = {}
    for key, raw_value in raw_filters.items():
        if key not in ALLOWED_FILTERS or key not in allowed_for_query or raw_value in (None, ""):
            continue
        if key == "release_year":
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            years = sorted({int(value) for value in values})
            if not years or any(year < 2000 or year > 2100 for year in years):
                raise DoraDbQueryRejected("release_year must be between 2000 and 2100")
            normalized[key] = years
        elif key == "release_date":
            value = str(raw_value).strip()
            try:
                normalized[key] = date.fromisoformat(value).isoformat()
            except ValueError as exc:
                raise DoraDbQueryRejected(
                    "release_date must use YYYY-MM-DD or DD/MM/YYYY"
                ) from exc
        elif key == "dcpsquad":
            value = str(raw_value).strip().upper()
            if not re.fullmatch(r"[A-Z][A-Z0-9_-]{1,30}", value):
                raise DoraDbQueryRejected("Invalid DoraDB squad")
            normalized[key] = value
        elif key == "jira_key":
            value = str(raw_value).strip().upper()
            if not re.fullmatch(r"[A-Z][A-Z0-9_]+-\d+", value):
                raise DoraDbQueryRejected("Invalid Jira key")
            normalized[key] = value
        elif key == "project_key":
            value = str(raw_value).strip().upper()
            if value != settings.doradb_project_key.upper():
                raise DoraDbQueryRejected("Only the configured DoraDB project is allowed")
            normalized[key] = value
        elif key in {"table_schema", "table_name", "column_search"}:
            value = str(raw_value).strip().lower()
            if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value):
                raise DoraDbQueryRejected(f"Invalid metadata filter: {key}")
            normalized[key] = value
        elif key == "age_days":
            value = int(raw_value)
            if not 1 <= value <= 3650:
                raise DoraDbQueryRejected("age_days must be between 1 and 3650")
            normalized[key] = value
        else:
            value = str(raw_value).strip()
            if len(value) > 120:
                raise DoraDbQueryRejected(f"{key} is too long")
            normalized[key] = value
    normalized["project_key"] = settings.doradb_project_key.upper()
    if query_id == "dora_metrics_by_squad" and "dcpsquad" not in normalized:
        raise DoraDbQueryRejected("dora_metrics_by_squad requires a squad filter")
    if query_id in LARGE_QUERY_IDS and not (
        set(normalized) & LARGE_QUERY_REQUIRED_FILTERS
    ):
        raise DoraDbQueryRejected(
            f"{query_id} requires a year, release, issue type, or Jira key filter"
        )
    return normalized


def _build_statement(
    query_id: str,
    filters: dict[str, Any],
    limit: int,
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "limit": limit,
        "project_key": filters["project_key"],
    }
    if query_id == "dora_metrics_by_squad":
        params["dcpsquad"] = filters["dcpsquad"]
    if query_id == "jira_unresolved_older_than_days":
        params["age_days"] = filters["age_days"]
    conditions: list[str] = []
    for key, column in _FILTER_COLUMNS[query_id].items():
        if key not in filters:
            continue
        value = filters[key]
        if key == "release_year":
            placeholders: list[str] = []
            for index, year in enumerate(value):
                parameter = f"release_year_{index}"
                placeholders.append(f":{parameter}")
                params[parameter] = year
            conditions.append(f"{column} IN ({', '.join(placeholders)})")
        elif key == "column_search":
            parameter = "filter_column_search"
            params[parameter] = f"%{value}%"
            conditions.append(f"LOWER(CAST({column} AS text)) LIKE :{parameter}")
        else:
            parameter = f"filter_{key}"
            params[parameter] = value
            conditions.append(f"LOWER(CAST({column} AS text)) = LOWER(:{parameter})")
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    projected_columns = ", ".join(
        f"approved.{column}"
        for column in QUERY_CATALOGUE[query_id]["expected_columns"]
    )
    statement = f"""
        SELECT {projected_columns}
        FROM ({_BASE_QUERIES[query_id]}) AS approved
        {where_clause}
        ORDER BY {_ORDER_BY[query_id]}
        LIMIT :limit
    """
    return statement, params


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def query_doradb(
    session: Session,
    *,
    query_id: str,
    filters: dict[str, Any] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Execute one approved query with bound parameters and a hard row limit."""

    if query_id not in APPROVED_QUERY_IDS:
        raise DoraDbQueryRejected("Unknown or unapproved DoraDB query ID")
    safe_filters = _normalize_filters(query_id, filters or {})
    catalogue_limit = int(QUERY_CATALOGUE[query_id]["default_limit"])
    maximum = 200 if query_id in LARGE_QUERY_IDS else settings.result_limit
    safe_limit = min(maximum, max(1, int(limit or catalogue_limit)))
    statement, params = _build_statement(query_id, safe_filters, safe_limit)
    rows = session.execute(text(statement), params).mappings().all()
    result_rows = [
        {key: _json_value(value) for key, value in row.items()} for row in rows
    ]
    expected = set(QUERY_CATALOGUE[query_id]["expected_columns"])
    if result_rows and not expected.issubset(result_rows[0]):
        missing = sorted(expected - set(result_rows[0]))
        raise DoraDbQueryRejected(
            f"Validated query result is missing expected fields: {', '.join(missing)}"
        )
    warnings: list[str] = []
    if query_id in {
        "feature_vs_release_frequency",
        "feature_vs_user_story",
        "story_to_feature_ratio",
    }:
        warnings.append(
            "The feature materialized view may be stale until an authorized refresh."
        )
    if query_id == "jira_distinct_squads":
        warnings.append(
            "Jira dcpsquad values are not confirmed as an authoritative "
            "organisation-wide squad directory."
        )
    return {
        "query_id": query_id,
        "project_key": safe_filters["project_key"],
        "filters": safe_filters,
        "rows": result_rows,
        "row_count": len(result_rows),
        "limit_applied": safe_limit,
        "warnings": warnings,
    }
