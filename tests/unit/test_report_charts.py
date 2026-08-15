"""Report charts are drawn, and their captions cannot contradict them."""

from __future__ import annotations

from backend.services.report_charts import (
    MAX_CATEGORIES,
    describe,
    draw_chart,
    rows_of,
    truncation_note,
)

BARS = {
    "type": "bar", "title": "Bugs by squad", "x_key": "squad",
    "series": [{"key": "bugs", "label": "Open bugs", "unit": "bugs"}],
    "data": [
        {"squad": "MBK", "bugs": 1434},
        {"squad": "JAEGER", "bugs": 1368},
        {"squad": "Elite", "bugs": 906},
    ],
}


def test_each_supported_chart_type_produces_a_drawing() -> None:
    for kind in ("bar", "horizontal_bar", "stacked_bar", "line", "area", "pie", "donut"):
        assert draw_chart({**BARS, "type": kind}, 460.0) is not None, kind


def test_an_unknown_type_still_draws_rather_than_vanishing() -> None:
    assert draw_chart({**BARS, "type": "something_new"}, 460.0) is not None


def test_a_chart_with_no_data_is_not_drawn() -> None:
    assert draw_chart({**BARS, "data": []}, 460.0) is None
    assert draw_chart({**BARS, "series": []}, 460.0) is None
    # A pie of nothing has no slices to draw.
    assert draw_chart({**BARS, "type": "pie", "data": [{"squad": "A", "bugs": 0}]}, 460.0) is None


def test_non_numeric_and_missing_values_do_not_break_the_plot() -> None:
    messy = {**BARS, "data": [{"squad": "A", "bugs": "n/a"}, {"squad": "B"}, {"squad": "C", "bugs": 5}]}
    assert draw_chart(messy, 460.0) is not None


def test_negative_values_are_plotted() -> None:
    negatives = {**BARS, "data": [{"squad": "A", "bugs": -12}, {"squad": "B", "bugs": 40}]}
    assert draw_chart(negatives, 460.0) is not None


def test_a_dense_chart_is_capped_and_says_so() -> None:
    dense = {**BARS, "data": [{"squad": f"S{i}", "bugs": i} for i in range(40)]}
    assert len(rows_of(dense)) == MAX_CATEGORIES
    note = truncation_note(dense)
    assert str(MAX_CATEGORIES) in note and "40" in note
    # Nothing is hidden silently when everything fits.
    assert truncation_note(BARS) == ""


def test_the_caption_states_only_what_the_data_says() -> None:
    caption = describe(BARS)
    assert "3 categories" in caption
    assert "MBK" in caption and "1,434" in caption
    assert "Elite" in caption and "906" in caption
    assert "3,708" in caption  # 1434 + 1368 + 906


def test_a_total_is_not_claimed_for_rates_or_durations() -> None:
    # Summing percentages or months would be meaningless.
    for unit in ("%", "months", "days"):
        chart = {
            **BARS,
            "series": [{"key": "bugs", "label": "Rate", "unit": unit}],
        }
        assert "Total" not in describe(chart), unit
    assert "Total" in describe(BARS)


def test_an_empty_chart_has_no_caption_to_contradict() -> None:
    assert describe({**BARS, "data": []}) == ""
    assert describe({**BARS, "series": []}) == ""


def test_multi_series_charts_are_announced() -> None:
    multi = {
        **BARS,
        "series": [
            {"key": "bugs", "label": "Open bugs", "unit": "bugs"},
            {"key": "done", "label": "Resolved", "unit": "bugs"},
        ],
        "data": [{"squad": "MBK", "bugs": 10, "done": 4}, {"squad": "SRE", "bugs": 2, "done": 9}],
    }
    assert "2 measures are plotted" in describe(multi)
    assert draw_chart(multi, 460.0) is not None


def test_templates_ask_for_charts_so_reports_are_not_all_prose() -> None:
    from backend.services.report_templates import TEMPLATES

    for key, template in TEMPLATES.items():
        questions = template["questions"]
        if not questions:
            continue
        assert any("chart" in q.lower() for q in questions), f"{key} asks for no visual"
