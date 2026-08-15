"""End-to-end Report Studio tests against a real (temporary) database.

Reports are persistent, user-scoped objects, so these run through the real
FastAPI app and a real SQLite file rather than mocking the repository -- the
ownership rules are the point, and mocking them out would test nothing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.db import Base, Conversation, ConversationMessage, get_db
from backend.main import app

USER_A = {"X-Development-Session": "user-alpha-0001"}
USER_B = {"X-Development-Session": "user-bravo-0002"}


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'reports.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        test_client.session_factory = TestingSession
        yield test_client
    app.dependency_overrides.clear()


def _seed_conversation(client, *, user_id: str, squad: str | None, answer: str, question: str):
    """Insert a conversation with one assistant answer carrying real evidence."""

    session = client.session_factory()
    conversation = Conversation(id=uuid.uuid4(), title=question[:60], user_id=user_id, state={})
    session.add(conversation)
    session.flush()
    session.add(
        ConversationMessage(
            conversation_id=conversation.id, role="user", content=question,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=2),
        )
    )
    assistant = ConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        created_at=datetime.now(timezone.utc),
        structured_content={
            "chart": {
                "type": "bar", "title": "Work status", "x_key": "status",
                "series": [{"key": "count", "label": "Tickets", "unit": "tickets"}],
                "data": [{"status": "To Do", "count": 120}, {"status": "Done", "count": 812}],
            },
            "table": {
                "title": "Detail",
                "columns": [{"key": "k", "label": "Ticket"}],
                "rows": [{"k": "DCPM-1"}, {"k": "DCPM-2"}],
            },
            "warnings": ["Done is an end state and may include cancelled work."],
            "validation": {"valid": True},
            "query_identifiers": ["jira_issue_counts_by_status"],
            "row_counts": [2],
            "knowledge_sections": ["Status and status category"],
            "metadata": {
                "dashboard_context": {"project": "DCPM", "squad": squad},
                "project_scope": {"project_key": "DCPM"},
                "generated_at": datetime.now(timezone.utc).isoformat(),
                # Must never reach a report: restricted personal fields.
                "assignee": "Jane Doe",
                "reporter": "John Smith",
            },
        },
    )
    session.add(assistant)
    session.commit()
    ids = (conversation.id, assistant.id)
    session.close()
    return ids


def _create(client, headers=USER_A, **body):
    response = client.post("/api/reports", json={"template": "sprint_performance", **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Creation, templates, ownership                                              #
# --------------------------------------------------------------------------- #


def test_templates_are_offered(client):
    payload = client.get("/api/reports/templates").json()
    ids = {template["id"] for template in payload["templates"]}
    assert {"executive_summary", "sprint_performance", "risk_and_action",
            "weekly_management_update", "dora_performance", "blank"} <= ids
    assert "senior_leadership" in payload["audiences"]
    assert "rewrite" in payload["content_modes"]


def test_create_report_from_template_builds_its_sections(client):
    report = _create(client, title="Sprint Report", scope={"project": "DCPM", "squad": "TITAN"})
    assert report["status"] == "draft"
    assert report["version"] == 1
    types = [section["type"] for section in report["sections"]]
    assert types[0] == "cover"
    assert "executive_summary" in types and "methodology" in types
    # Positions are contiguous and ordered.
    assert [s["position"] for s in report["sections"]] == list(range(1, len(types) + 1))


def test_unknown_template_is_rejected(client):
    response = client.post("/api/reports", json={"template": "not_a_template"}, headers=USER_A)
    assert response.status_code == 422


def test_a_report_is_not_reachable_by_another_user(client):
    report = _create(client)
    assert client.get(f"/api/reports/{report['id']}", headers=USER_A).status_code == 200
    # Same 404 as a missing report: confirming it exists would itself leak.
    assert client.get(f"/api/reports/{report['id']}", headers=USER_B).status_code == 404
    assert client.patch(
        f"/api/reports/{report['id']}", json={"title": "hijacked"}, headers=USER_B
    ).status_code == 404
    assert client.delete(f"/api/reports/{report['id']}", headers=USER_B).status_code == 404


def test_listing_only_returns_your_own_reports(client):
    _create(client, headers=USER_A, title="Alpha report")
    _create(client, headers=USER_B, title="Bravo report")
    titles = {r["title"] for r in client.get("/api/reports", headers=USER_A).json()["reports"]}
    assert titles == {"Alpha report"}


def test_missing_report_returns_404_not_500(client):
    assert client.get(f"/api/reports/{uuid.uuid4()}", headers=USER_A).status_code == 404


# --------------------------------------------------------------------------- #
# Sources, provenance, privacy                                                #
# --------------------------------------------------------------------------- #


def test_adding_an_authorized_message_snapshots_its_evidence(client):
    conversation_id, message_id = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="How is TITAN progressing?", answer="TITAN has 812 done and 120 to do.",
    )
    report = _create(client)
    response = client.post(
        f"/api/reports/{report['id']}/sources",
        json={"conversation_id": str(conversation_id), "message_id": str(message_id)},
        headers=USER_A,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["sources"]) == 1
    source = body["sources"][0]
    assert source["query_ids"] == ["jira_issue_counts_by_status"]
    assert source["row_counts"] == [2]
    assert source["has_chart"] and source["has_table"]
    assert source["scope"]["squad"] == "TITAN"
    assert source["conversation_id"] == str(conversation_id)
    assert source["message_id"] == str(message_id)
    # A full selection becomes chart + table + narrative blocks.
    added = [s for s in body["sections"] if s["source_ids"]]
    assert {s["type"] for s in added} == {"chart", "data_table", "key_finding"}


def test_restricted_fields_never_enter_a_report(client):
    conversation_id, message_id = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="Who is working on this?", answer="Two people are assigned.",
    )
    report = _create(client)
    client.post(
        f"/api/reports/{report['id']}/sources",
        json={"conversation_id": str(conversation_id), "message_id": str(message_id)},
        headers=USER_A,
    )
    session = client.session_factory()
    from backend.database.db import ReportSource

    stored = session.query(ReportSource).one()
    serialized = str(stored.evidence)
    session.close()
    for restricted in ("assignee", "reporter", "Jane Doe", "John Smith"):
        assert restricted not in serialized, f"{restricted!r} leaked into the evidence snapshot"


def test_a_message_from_another_users_conversation_is_rejected(client):
    conversation_id, message_id = _seed_conversation(
        client, user_id="user-bravo-0002", squad="TITAN",
        question="Bravo's question", answer="Bravo's answer",
    )
    report = _create(client, headers=USER_A)
    response = client.post(
        f"/api/reports/{report['id']}/sources",
        json={"conversation_id": str(conversation_id), "message_id": str(message_id)},
        headers=USER_A,
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_a_user_message_cannot_be_used_as_evidence(client):
    session = client.session_factory()
    conversation = Conversation(id=uuid.uuid4(), title="t", user_id="user-alpha-0001", state={})
    session.add(conversation)
    session.flush()
    message = ConversationMessage(conversation_id=conversation.id, role="user", content="hello")
    session.add(message)
    session.commit()
    ids = (conversation.id, message.id)
    session.close()

    report = _create(client)
    response = client.post(
        f"/api/reports/{report['id']}/sources",
        json={"conversation_id": str(ids[0]), "message_id": str(ids[1])},
        headers=USER_A,
    )
    assert response.status_code == 422


def test_sources_combine_across_messages_and_conversations(client):
    first = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="TITAN progress?", answer="TITAN is at 43%.",
    )
    second = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="TITAN bugs?", answer="TITAN has 12 open bugs.",
    )
    report = _create(client)
    for conversation_id, message_id in (first, second):
        response = client.post(
            f"/api/reports/{report['id']}/sources",
            json={"conversation_id": str(conversation_id), "message_id": str(message_id),
                  "selection": "narrative"},
            headers=USER_A,
        )
        assert response.status_code == 201
    body = client.get(f"/api/reports/{report['id']}", headers=USER_A).json()
    assert len(body["sources"]) == 2
    assert len({s["conversation_id"] for s in body["sources"]}) == 2


def test_conflicting_scopes_are_reported_and_never_merged_silently(client):
    titan = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="TITAN progress?", answer="TITAN is at 43%.",
    )
    everyone = _seed_conversation(
        client, user_id="user-alpha-0001", squad=None,
        question="Overall progress?", answer="The project is at 61%.",
    )
    report = _create(client)
    for conversation_id, message_id in (titan, everyone):
        client.post(
            f"/api/reports/{report['id']}/sources",
            json={"conversation_id": str(conversation_id), "message_id": str(message_id),
                  "selection": "narrative"},
            headers=USER_A,
        )
    body = client.get(f"/api/reports/{report['id']}", headers=USER_A).json()
    squad_conflicts = [c for c in body["conflicts"] if c["field"] == "squad"]
    assert squad_conflicts, "a squad-vs-all-squads difference must surface"
    assert "TITAN" in squad_conflicts[0]["message"]


# --------------------------------------------------------------------------- #
# Sections: edit, reorder, manual-edit state                                  #
# --------------------------------------------------------------------------- #


def test_sections_can_be_added_hidden_reordered_and_removed(client):
    report = _create(client)
    added = client.post(
        f"/api/reports/{report['id']}/sections",
        json={"type": "rich_text", "title": "Context", "content": "Background."},
        headers=USER_A,
    ).json()
    section = next(s for s in added["sections"] if s["title"] == "Context")

    hidden = client.patch(
        f"/api/reports/{report['id']}/sections/{section['id']}",
        json={"visible": False}, headers=USER_A,
    ).json()
    assert next(s for s in hidden["sections"] if s["id"] == section["id"])["visible"] is False

    order = [s["id"] for s in hidden["sections"]]
    reversed_order = list(reversed(order))
    reordered = client.post(
        f"/api/reports/{report['id']}/sections/reorder",
        json={"section_ids": reversed_order}, headers=USER_A,
    ).json()
    assert [s["id"] for s in reordered["sections"]] == reversed_order
    assert [s["position"] for s in reordered["sections"]] == list(range(1, len(order) + 1))

    removed = client.delete(
        f"/api/reports/{report['id']}/sections/{section['id']}", headers=USER_A
    ).json()
    assert section["id"] not in [s["id"] for s in removed["sections"]]
    # Positions stay contiguous after a deletion.
    assert [s["position"] for s in removed["sections"]] == list(
        range(1, len(removed["sections"]) + 1)
    )


def test_unknown_section_type_is_rejected(client):
    report = _create(client)
    response = client.post(
        f"/api/reports/{report['id']}/sections",
        json={"type": "malicious_block"}, headers=USER_A,
    )
    assert response.status_code == 422


def test_editing_a_validated_fact_marks_it_for_review(client):
    conversation_id, message_id = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="Status?", answer="812 tickets are done.",
    )
    report = _create(client)
    body = client.post(
        f"/api/reports/{report['id']}/sources",
        json={"conversation_id": str(conversation_id), "message_id": str(message_id),
              "selection": "narrative", "content_mode": "original"},
        headers=USER_A,
    ).json()
    section = next(s for s in body["sections"] if s["source_ids"])
    assert section["needs_review"] is False

    edited = client.patch(
        f"/api/reports/{report['id']}/sections/{section['id']}",
        json={"content": "900 tickets are done."}, headers=USER_A,
    ).json()
    updated = next(s for s in edited["sections"] if s["id"] == section["id"])
    # A hand-edited number can no longer claim to be evidence-verified.
    assert updated["manually_edited"] is True
    assert updated["needs_review"] is True
    assert edited["status"] == "needs_review"


# --------------------------------------------------------------------------- #
# Validation, duplication, export                                             #
# --------------------------------------------------------------------------- #


def test_validation_flags_a_report_with_no_evidence(client):
    report = _create(client)
    body = client.post(f"/api/reports/{report['id']}/validate", headers=USER_A).json()
    assert body["validation"]["state"] == "attention"
    assert any("no evidence" in issue.lower() for issue in body["validation"]["issues"])


def test_duplicating_copies_sections_and_evidence(client):
    conversation_id, message_id = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="Status?", answer="812 done.",
    )
    report = _create(client, title="Week 1")
    client.post(
        f"/api/reports/{report['id']}/sources",
        json={"conversation_id": str(conversation_id), "message_id": str(message_id)},
        headers=USER_A,
    )
    original = client.get(f"/api/reports/{report['id']}", headers=USER_A).json()
    copy = client.post(
        f"/api/reports/{report['id']}/duplicate", json={"title": "Week 2"}, headers=USER_A
    ).json()

    assert copy["id"] != original["id"]
    assert copy["title"] == "Week 2"
    assert copy["status"] == "draft"
    assert len(copy["sections"]) == len(original["sections"])
    assert len(copy["sources"]) == len(original["sources"])
    # Copied sections must point at the copy's own snapshots.
    copy_source_ids = {s["id"] for s in copy["sources"]}
    original_source_ids = {s["id"] for s in original["sources"]}
    assert copy_source_ids.isdisjoint(original_source_ids)
    for section in copy["sections"]:
        assert set(section["source_ids"]) <= copy_source_ids


def test_pdf_export_returns_a_real_pdf(client):
    report = _create(client, title="Sprint Performance Report")
    response = client.post(
        f"/api/reports/{report['id']}/export", json={"format": "pdf"}, headers=USER_A
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert "attachment;" in response.headers["content-disposition"]
    assert ".pdf" in response.headers["content-disposition"]
    # Exporting advances the lifecycle so the library can show it.
    assert client.get(f"/api/reports/{report['id']}", headers=USER_A).json()["status"] == "exported"


def test_docx_export_returns_a_word_document(client):
    report = _create(client, title="Sprint Performance Report")
    response = client.post(
        f"/api/reports/{report['id']}/export", json={"format": "docx"}, headers=USER_A
    )
    assert response.status_code == 200
    # DOCX is a zip container.
    assert response.content[:2] == b"PK"


def test_csv_export_returns_the_table_rows(client):
    conversation_id, message_id = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="Show the tickets", answer="Here they are.",
    )
    report = _create(client)
    body = client.post(
        f"/api/reports/{report['id']}/sources",
        json={"conversation_id": str(conversation_id), "message_id": str(message_id),
              "selection": "table"},
        headers=USER_A,
    ).json()
    table = next(
        s for s in body["sections"] if s["type"] == "data_table" and s["source_ids"]
    )
    response = client.post(
        f"/api/reports/{report['id']}/export",
        json={"format": "csv", "section_id": table["id"]}, headers=USER_A,
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    text = response.content.decode("utf-8-sig")
    assert "Ticket" in text and "DCPM-1" in text


def test_csv_export_requires_a_tabular_section(client):
    report = _create(client)
    summary = next(s for s in report["sections"] if s["type"] == "executive_summary")
    response = client.post(
        f"/api/reports/{report['id']}/export",
        json={"format": "csv", "section_id": summary["id"]}, headers=USER_A,
    )
    assert response.status_code == 422


def test_export_of_another_users_report_is_refused(client):
    report = _create(client, headers=USER_A)
    response = client.post(
        f"/api/reports/{report['id']}/export", json={"format": "pdf"}, headers=USER_B
    )
    assert response.status_code == 404


def test_a_report_survives_reload(client):
    """The persistence requirement: a draft is still there on a fresh request."""

    report = _create(client, title="Persisted report")
    client.patch(f"/api/reports/{report['id']}", json={"title": "Renamed"}, headers=USER_A)
    reopened = client.get(f"/api/reports/{report['id']}", headers=USER_A).json()
    assert reopened["title"] == "Renamed"
    assert len(reopened["sections"]) == len(report["sections"])


def test_visuals_land_with_the_analysis_not_in_a_heap_at_the_end(client):
    """A chart belongs beside the section it illustrates.

    Appending every visual produced a report of prose followed by a block of
    unexplained diagrams, with the data-quality and methodology blocks stranded
    above them.
    """

    conversation_id, message_id = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="Show the work status", answer="Mostly done.",
    )
    report = _create(client)  # sprint_performance: reserves a chart and a table slot
    body = client.post(
        f"/api/reports/{report['id']}/sources",
        json={"conversation_id": str(conversation_id), "message_id": str(message_id)},
        headers=USER_A,
    ).json()

    sections = sorted(body["sections"], key=lambda s: s["position"])
    charts = [s for s in sections if s["type"] == "chart" and s["payload"]]
    tables = [s for s in sections if s["type"] == "data_table" and s["payload"]]
    assert charts and tables

    # The template already reserved a slot for each, so they filled it rather
    # than creating duplicates at the end.
    assert len([s for s in sections if s["type"] == "chart"]) == 1
    assert len([s for s in sections if s["type"] == "data_table"]) == 1

    # And they sit above the closing blocks, not after them.
    closing = [
        s["position"] for s in sections if s["type"] in {"data_quality", "methodology"}
    ]
    assert closing
    assert charts[0]["position"] < min(closing)
    assert tables[0]["position"] < min(closing)


def test_extra_visuals_go_before_the_closing_blocks(client):
    """With no placeholder left, a second chart still lands in the body."""

    report = _create(client, template="weekly_management_update")  # no chart slot
    first = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="First question", answer="First answer.",
    )
    second = _seed_conversation(
        client, user_id="user-alpha-0001", squad="TITAN",
        question="Second question", answer="Second answer.",
    )
    for conversation_id, message_id in (first, second):
        body = client.post(
            f"/api/reports/{report['id']}/sources",
            json={"conversation_id": str(conversation_id), "message_id": str(message_id),
                  "selection": "chart"},
            headers=USER_A,
        ).json()

    sections = sorted(body["sections"], key=lambda s: s["position"])
    charts = [s for s in sections if s["type"] == "chart"]
    closing = [s["position"] for s in sections if s["type"] == "methodology"]
    # Both charts are kept -- "if there are a lot of diagrams, put them all".
    assert len(charts) == 2
    assert all(chart["position"] < min(closing) for chart in charts)
    # Positions stay contiguous after the inserts.
    assert [s["position"] for s in sections] == list(range(1, len(sections) + 1))
