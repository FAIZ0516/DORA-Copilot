"""End-to-end Report Studio tests against a real (temporary) database.

Reports are persistent, user-scoped objects, so these run through the real
FastAPI app and a real SQLite file rather than mocking the repository -- the
ownership rules are the point, and mocking them out would test nothing.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.db import Base, Conversation, ConversationMessage, get_db
from backend.main import app
from backend.report_repository import ReportRepository

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
            "weekly_management_update", "weekly_scrum", "dora_performance", "blank"} <= ids
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


def test_weekly_scrum_starts_with_deterministic_needs_input_states(client):
    report = _create(
        client, template="weekly_scrum",
        scope={"project": "DCPM", "squad": "TITAN", "sprint": "Sprint 24"},
    )
    feature = next(section for section in report["sections"] if section["type"] == "feature_status")
    assert feature["state"] == "needs_input"
    assert feature["state_reason"]


def test_unknown_template_is_rejected(client):
    response = client.post("/api/reports", json={"template": "not_a_template"}, headers=USER_A)
    assert response.status_code == 422


def test_weekly_scrum_template_can_be_applied_inside_the_same_report(client):
    report = _create(client, template="executive_summary", title="KAIJU Delivery Report")
    response = client.post(
        f"/api/reports/{report['id']}/template",
        json={"template": "weekly_scrum"},
        headers=USER_A,
    )
    assert response.status_code == 200, response.text
    applied = response.json()
    assert applied["id"] == report["id"]
    assert applied["template"] == "weekly_scrum"
    assert [section["type"] for section in applied["sections"]] == [
        "cover", "feature_status", "executive_summary", "key_finding", "action_list",
    ]


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


def test_refinement_updates_only_the_selected_section(client, monkeypatch):
    report = _create(client, template="executive_summary")
    session = client.session_factory()
    repository = ReportRepository(session)
    stored = repository.get(uuid.UUID(report["id"]), user_id="user-alpha-0001")
    source = repository.add_source(
        stored,
        conversation_id=None,
        message_id=None,
        selection="full",
        evidence={"answer": "KAIJU has completed 812 tickets.", "warnings": []},
        scope={"project": "DCPM", "squad": "KAIJU"},
        data_as_of=datetime.now(timezone.utc),
    )
    summary = next(section for section in stored.sections if section.type == "executive_summary")
    other = next(section for section in stored.sections if section.type == "key_finding")
    summary.content = "KAIJU has completed 812 tickets across the verified scope."
    summary.source_ids = [str(source.id)]
    other.content = "This other section must remain unchanged."
    other.source_ids = [str(source.id)]
    selected_id = str(summary.id)
    other_id = str(other.id)
    session.commit()
    session.close()

    class RefiningProvider:
        enabled = True

        def complete(self, *_args, **_kwargs):
            return (
                '{"section":{"section_id":"' + selected_id + '","title":"Executive Summary",'
                '"content":"KAIJU has completed 812 tickets."}}'
            )

    from backend.api import reports as reports_api
    monkeypatch.setattr(reports_api, "GenerativeAIClient", lambda *_args, **_kwargs: RefiningProvider())

    response = client.post(
        f"/api/reports/{report['id']}/refine",
        json={"section_id": selected_id, "instruction": "Make this shorter."},
        headers=USER_A,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["updated_sections"] == [selected_id]
    by_id = {section["id"]: section for section in body["report"]["sections"]}
    assert by_id[selected_id]["content"] == "KAIJU has completed 812 tickets."
    assert by_id[other_id]["content"] == "This other section must remain unchanged."


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


def test_pdf_preview_uses_the_export_renderer_without_marking_exported(client, monkeypatch):
    from backend.api import reports as reports_api

    calls = []
    monkeypatch.setattr(reports_api, "render_pdf", lambda payload: calls.append(payload["id"]) or b"%PDF-preview")
    report = _create(client, title="Preview Report")
    response = client.post(
        f"/api/reports/{report['id']}/export",
        json={"format": "pdf", "preview": True},
        headers=USER_A,
    )
    assert response.status_code == 200
    assert response.content == b"%PDF-preview"
    assert response.headers["content-disposition"].startswith("inline;")
    reopened = client.get(f"/api/reports/{report['id']}", headers=USER_A).json()
    assert reopened["status"] == "draft"
    assert reopened["last_exported_at"] is None
    assert [str(value) for value in calls] == [report["id"]]


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


def test_regeneration_replaces_prior_generated_evidence(client):
    report = _create(client)
    session = client.session_factory()
    repository = ReportRepository(session)
    stored = repository.get(uuid.UUID(report["id"]), user_id="user-alpha-0001")
    for run in (1, 2):
        repository.replace_generated_content(stored)
        repository.add_source(
            stored, conversation_id=None, message_id=None, selection="full",
            evidence={"generated_by": "report_template", "answer": f"Run {run}"},
            scope={"project": "DCPM"}, data_as_of=datetime.now(timezone.utc),
        )
        session.refresh(stored)
        generated = [source for source in stored.sources if source.evidence.get("generated_by") == "report_template"]
        assert len(generated) == 1
    session.close()


def _verified_current_view_snapshot() -> dict:
    content = {
        "executive_summary": {"content": "JAEGER has 2,682 scoped tickets and is 92.47% in Done."},
        "kpi_group": {
            "payload": {
                "state": "ready",
                "items": [{"key": "completion_pct", "label": "Sprint Completion", "value": "92.47%", "raw_value": 92.47}],
                "columns": [{"key": "label", "label": "Measure"}, {"key": "value", "label": "Value"}],
                "rows": [{"label": "Sprint Completion", "value": "92.47%"}],
            }
        },
        "key_finding": {"content": "202 tickets remain open."},
        "risk": {"content": "16 tickets are currently in Impeded status."},
        "recommendation": {"content": "Review the impeded tickets and record a next action."},
        "action_list": {"content": "Review the impeded tickets and record a next action."},
        "data_quality": {"content": "Done is an end-state category."},
        "methodology": {"content": "Recalculated server-side from read-only DoraDB."},
    }
    return {
        "state": "ready",
        "scope": {"project": "DCPM", "squad": "JAEGER"},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence": {
            "generated_by": "report_template",
            "evidence_type": "verified_dashboard_snapshot",
            "question": "Verified current dashboard snapshot",
            "answer": "JAEGER has 2,682 scoped tickets and is 92.47% in Done. 202 remain open and 16 are Impeded.",
            "query_ids": ["dashboard_service.get_squad_dashboard"],
            "row_counts": [2682],
            "validation": {"valid": True},
            "warnings": [],
        },
        "sections": content,
    }


def _enable_current_view_generation(monkeypatch):
    from backend.api import reports as reports_api

    @contextmanager
    def fake_doradb():
        yield object()

    class NoNarrativeProvider:
        enabled = False

        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(reports_api.settings, "doradb_user", "report-test")
    monkeypatch.setattr(reports_api.settings, "doradb_password", "report-test")
    monkeypatch.setattr(reports_api, "doradb_session", fake_doradb)
    monkeypatch.setattr(reports_api, "GenerativeAIClient", NoNarrativeProvider)
    monkeypatch.setattr(
        reports_api, "current_view_dashboard_evidence",
        lambda *_args, **_kwargs: _verified_current_view_snapshot(),
    )
    monkeypatch.setattr(
        reports_api, "run_template_questions",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Current View must not ask broad agent questions")),
    )
    return reports_api


def test_current_view_generates_from_dashboard_without_chat_evidence(client, monkeypatch):
    _enable_current_view_generation(monkeypatch)
    report = _create(
        client,
        template="executive_summary",
        title="JAEGER Delivery Report",
        scope={
            "project": "dcpm", "squad": "JAEGER",
            "sprint": "All sprints", "release": "All releases",
            "current_metric_value": 999999,
        },
    )
    assert report["sources"] == []
    assert report["scope"] == {"project": "DCPM", "squad": "JAEGER"}

    first = client.post(f"/api/reports/{report['id']}/generate", headers=USER_A)
    assert first.status_code == 200, first.text
    body = first.json()["report"]
    assert len(body["sources"]) == 1
    assert body["sources"][0]["query_ids"] == ["dashboard_service.get_squad_dashboard"]
    states = {section["type"]: section["state"] for section in body["sections"]}
    for section_type in (
        "executive_summary", "kpi_group", "key_finding", "risk",
        "recommendation", "data_quality", "methodology",
    ):
        assert states[section_type] == "ready"

    second = client.post(f"/api/reports/{report['id']}/generate", headers=USER_A)
    assert second.status_code == 200, second.text
    assert len(second.json()["report"]["sources"]) == 1


def test_weekly_scrum_only_leaves_unsupported_feature_status_needing_input(client, monkeypatch):
    reports_api = _enable_current_view_generation(monkeypatch)
    monkeypatch.setattr(
        reports_api,
        "weekly_scrum_feature_evidence",
        lambda *_args, **_kwargs: {
            "state": "needs_input",
            "reason": "No Feature issues with a verified status were found for this squad and sprint.",
            "rows": [],
        },
    )
    report = _create(
        client,
        template="weekly_scrum",
        scope={"project": "DCPM", "squad": "JAEGER", "sprint": "Sprint 24"},
    )
    response = client.post(f"/api/reports/{report['id']}/generate", headers=USER_A)
    assert response.status_code == 200, response.text
    states = {section["type"]: section["state"] for section in response.json()["report"]["sections"]}
    assert states["feature_status"] == "needs_input"
    assert states["executive_summary"] == "ready"
    assert states["key_finding"] == "ready"
    assert states["action_list"] == "ready"


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
