from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.agent_system.graph import AdvancedDoraDbAgent
from backend.agent_system.request_router import route_jira_request
from backend.agent_system.result_cache import build_cache_entry, choose_cache_action
from backend.conversation_context import update_persistent_state
from backend.conversation_repository import ConversationRepository
from backend.db import Base


def cache_entry(rows=None, project="DCPM"):
    rows = rows or [{"dcpsquad": "TITAN", "missing_squad_rows": 2}]
    return build_cache_entry(
        intent="DATA_RETRIEVAL",
        project_scope={"project_key": project},
        results=[{
            "query_id": "jira_distinct_squads",
            "filters": {"project_key": project},
            "rows": rows,
            "row_count": len(rows),
            "limit_applied": 100,
            "warnings": [],
        }],
    )


def test_conversation_persists_reopens_and_is_user_scoped():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        repo = ConversationRepository(session)
        conversation = repo.create(
            user_id="development-user-a", workspace="business",
            project_scope={"project_key": "DCPM"}, first_question="Show delivery risks",
        )
        repo.add_message(conversation, role="user", content="Show delivery risks")
        reopened = repo.get(conversation.id, user_id="development-user-a", include_messages=True)
        assert reopened is not None
        assert reopened.state["workspace"] == "business"
        assert reopened.state["project_scope"] == {"project_key": "DCPM"}
        assert [item.content for item in reopened.messages] == ["Show delivery risks"]
        assert repo.get(conversation.id, user_id="development-user-b") is None


def test_new_conversation_does_not_delete_previous_and_archive_is_scoped():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        repo = ConversationRepository(session)
        first = repo.create(user_id="development-user-a", workspace="technical", project_scope={})
        second = repo.create(user_id="development-user-a", workspace="technical", project_scope={})
        assert {item.id for item in repo.list_recent(user_id="development-user-a")} == {first.id, second.id}
        repo.archive(second)
        assert [item.id for item in repo.list_recent(user_id="development-user-a")] == [first.id]


def test_follow_up_reuses_fresh_result_without_database_query():
    entry = cache_entry()
    assert entry is not None
    result = AdvancedDoraDbAgent(None).chat(
        "How many did you find?", session_id="conversation-cache-test",
        persistent_context={"query_cache": [entry]},
        project_scope={"project_key": "DCPM"},
    )
    assert "1 distinct non-empty squad" in result["answer"]
    assert result["intent"] == "FOLLOW_UP_ON_EXISTING_RESULT"
    assert result["metadata"]["query_result_reused"] is True
    assert result["metadata"]["database_query_executed"] is False


def test_squad_follow_up_does_not_count_schema_source_rows():
    entry = build_cache_entry(
        intent="DATA_RETRIEVAL", project_scope={"project_key": "DCPM"},
        results=[
            {
                "query_id": "database_squad_sources", "filters": {"project_key": "DCPM"},
                "rows": [{"column_name": "dcpsquad"}] * 3, "row_count": 3,
            },
            {
                "query_id": "jira_distinct_squads", "filters": {"project_key": "DCPM"},
                "rows": [{"dcpsquad": "TITAN", "missing_squad_rows": 2}], "row_count": 1,
            },
        ],
    )
    result = AdvancedDoraDbAgent(None).chat(
        "How many did you find?", session_id="multi-result-cache-test",
        persistent_context={"query_cache": [entry]},
        project_scope={"project_key": "DCPM"},
    )
    assert result["answer"].startswith("I found 1 distinct non-empty squad value")


def test_refresh_and_changed_scope_invalidate_reuse():
    memory = {"query_cache": [cache_entry()]}
    refresh = choose_cache_action(
        "Refresh the list.", memory=memory, project_scope={"project_key": "DCPM"}
    )
    changed = choose_cache_action(
        "How many did you find?", memory=memory, project_scope={"project_key": "OTHER"}
    )
    assert refresh.action == "refresh"
    assert changed.action == "none" and changed.reason == "scope_changed"


def test_zero_rows_are_not_cached_and_sensitive_fields_are_removed():
    assert build_cache_entry(
        intent="DATA_RETRIEVAL", project_scope={},
        results=[{"query_id": "jira_distinct_squads", "rows": [], "row_count": 0}],
    ) is None
    entry = cache_entry([{"dcpsquad": "TITAN", "summary": "secret", "assignee": "person"}])
    assert entry is not None
    assert entry["results"][0]["rows"][0] == {"dcpsquad": "TITAN"}


def test_long_summary_retains_scope_filters_and_warnings():
    updated = update_persistent_state(
        {"turn_count": 10, "summary": "Earlier definition retained."},
        workspace="business", project_scope={"project_key": "DCPM"},
        question="Show only bugs for TITAN last month", answer="Five bugs were observed.",
        agent_persistence={
            "intent": "ANALYSIS", "results": [], "query_result_reused": False,
            "last_context": {
                "filters": {"issuetype": "Bug", "dcpsquad": "TITAN", "date_range": "last month"},
                "query_ids": ["jira_bug_counts_by_squad"],
                "warnings": ["Coverage is incomplete."],
            },
        },
    )
    assert "DCPM" in updated["summary"]
    assert "TITAN" in updated["summary"] and "Bug" in updated["summary"]
    assert "Coverage is incomplete" in updated["summary"]


def test_bug_ranking_uses_grouped_query_not_squad_list():
    plan = route_jira_request("Which squad has the most bugs?")
    assert plan is not None
    assert [action["query_id"] for action in plan["actions"]] == ["jira_bug_counts_by_squad"]
