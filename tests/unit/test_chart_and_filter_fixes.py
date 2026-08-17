"""A chart must describe the rows it was given, and a field name is not a value."""

from __future__ import annotations

from backend.services import select_metric
from backend.services.chart_generation import build_chart_spec
from backend.services.filter_extraction import extract_filters


def status_of(message: str) -> str | None:
    return extract_filters(message, project_key="DCPM").get("status")


def test_the_field_name_status_category_is_not_read_as_a_status_value() -> None:
    # "by status category" extracted status="category", the plan was rejected as
    # an unknown entity, and the user got a clarifying question instead of a
    # chart.
    assert status_of("Show a bar chart of work by status category.") is None
    assert status_of("Break the work down by status categories") is None
    assert status_of("Show the status distribution") is None
    assert status_of("Give me a status breakdown") is None
    assert status_of("Show the status counts") is None


def test_a_real_status_is_still_extracted() -> None:
    assert status_of("Show issues where status is Impeded") == "Impeded"
    assert status_of("How many tickets have status Done?") == "Done"
    assert status_of("List work with status In Progress") == "In Progress"


BUGS_BY_PRIORITY = [
    {"priority": "High", "open_bugs": 12},
    {"priority": "Medium", "open_bugs": 40},
    {"priority": "Low", "open_bugs": 7},
]


def test_the_fallback_charts_the_rows_it_was_actually_given() -> None:
    # It used to count every result by `issuetype` whatever the query returned,
    # so rows without that column collapsed into one "Unknown" bar titled
    # "Returned Jira references by issue type" -- a chart contradicting the
    # answer above it.
    chart = build_chart_spec(
        query_id="jira_prioritized_open_bugs",
        rows=BUGS_BY_PRIORITY,
        metric=select_metric("open bugs"),
        question="Show a bar chart of open bugs by priority.",
    )
    assert chart is not None
    assert "issue type" not in chart["title"].lower()
    assert "priority" in chart["title"].lower()
    assert [point["category"] for point in chart["data"]] == ["High", "Medium", "Low"]
    assert [point["value"] for point in chart["data"]] == [12, 40, 7]
    # Every plotted point must be real, not an "Unknown" placeholder.
    assert all(point["category"] != "Unknown" for point in chart["data"])


def test_rows_with_no_measure_are_charted_as_counts() -> None:
    chart = build_chart_spec(
        query_id="some_listing_query",
        rows=[{"squad": "MBK"}, {"squad": "MBK"}, {"squad": "SRE"}],
        metric=select_metric("open bugs"),
        question="Show a bar chart of the rows by squad.",
    )
    assert chart is not None
    assert "squad" in chart["title"].lower()
    counts = {point["category"]: point["count"] for point in chart["data"]}
    assert counts == {"MBK": 2, "SRE": 1}


def test_rows_with_nothing_to_categorise_produce_no_chart() -> None:
    # A misleading chart is worse than none.
    assert (
        build_chart_spec(
            query_id="some_numeric_query",
            rows=[{"total": 5}, {"total": 9}],
            metric=select_metric("open bugs"),
            question="Show a bar chart.",
        )
        is None
    )


def test_no_rows_still_produces_no_chart() -> None:
    assert (
        build_chart_spec(
            query_id="anything",
            rows=[],
            metric=select_metric("open bugs"),
            question="Show a bar chart.",
        )
        is None
    )


def test_a_line_request_on_categorical_rows_falls_back_to_bars() -> None:
    chart = build_chart_spec(
        query_id="jira_prioritized_open_bugs",
        rows=BUGS_BY_PRIORITY,
        metric=select_metric("open bugs"),
        question="Show a line chart of open bugs by priority.",
    )
    assert chart is not None
    # Joining unordered categories with a line would imply a trend that is not
    # there.
    assert chart["type"] == "bar"


def test_generated_titles_use_report_language_not_column_names() -> None:
    chart = build_chart_spec(
        query_id="some_query",
        rows=[{"jira_key": "DCPM-1", "age_days": 1441}, {"jira_key": "DCPM-2", "age_days": 464}],
        metric=select_metric("open bugs"),
        question="Show a bar chart.",
    )
    assert chart is not None
    lowered = f"{chart['title']} {chart['x_label']}".lower()
    # A reader should never see the warehouse's spelling.
    for raw in ("jira_key", "age_days", "dcpsquad", "issuetype", "fixversions"):
        assert raw not in lowered
    assert "ticket" in lowered
