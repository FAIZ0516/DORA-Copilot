from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.agent.agent_definition import AdvancedDoraDbAgent


class _EchoFactsLlm:
    """A deterministic stand-in LLM: echoes the supplied computed facts as
    plain text instead of calling a real provider, so tests that exercise
    the follow-up path stay fast and offline. Real wording/tone is a
    provider concern verified separately (e.g. tests/unit/test_advanced_system.py);
    these integration tests only need the *facts* to survive the trip."""

    enabled = True
    source = "test-provider:echo"

    @staticmethod
    def complete(_system_prompt: str, user_prompt: str, **_kwargs: object) -> str:
        import json

        if not user_prompt.lstrip().startswith("{"):
            return (
                '{"mode":"conversation",'
                '"intent":"FOLLOW_UP_ON_EXISTING_RESULT",'
                '"confidence":0.99,"reason":"The user is asking about the '
                'available cached evidence.","clarification":"","actions":[]}'
            )
        payload = json.loads(user_prompt)
        facts = payload.get("computed_facts") or {}
        if "distinct_squad_count" in facts:
            text = (
                f"I found {facts['distinct_squad_count']} "
                "distinct non-empty squad values."
            )
            if facts.get("missing_squad_rows"):
                text += (
                    f" There are also {facts['missing_squad_rows']} Jira rows "
                    "without a populated squad value, so this list is not "
                    "complete coverage."
                )
            return text
        if "squad_methodology_note" in facts:
            return facts["squad_methodology_note"]
        return "The previous result is still available."
from backend.agent.request_router import route_jira_request
from backend.memory.result_cache import build_cache_entry, choose_cache_action
from backend.conversation_context import update_persistent_state
from backend.conversation_repository import ConversationRepository
from backend.database.db import Base


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
    agent = AdvancedDoraDbAgent(None)
    agent.llm = _EchoFactsLlm()  # type: ignore[assignment]
    agent.responder.llm = agent.llm
    result = agent.chat(
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
    agent = AdvancedDoraDbAgent(None)
    agent.llm = _EchoFactsLlm()  # type: ignore[assignment]
    agent.responder.llm = agent.llm  # the compiled graph already holds this
    # Responder instance; mutate its llm attribute rather than replacing
    # the Responder object, which the graph's node bindings wouldn't see.
    result = agent.chat(
        "How many did you find?", session_id="multi-result-cache-test",
        persistent_context={"query_cache": [entry]},
        project_scope={"project_key": "DCPM"},
    )
    # The response-protocol phrase configured in
    # backend/agent/INSTRUCTIONS.md is always prepended; assert on the
    # generated content rather than the exact start of the string.
    assert "I found 1 distinct non-empty squad value" in result["answer"]


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


def test_semantic_follow_up_can_reuse_cache_without_keyword_match():
    decision = choose_cache_action(
        "Could you expand on the number you just gave me?",
        memory={"query_cache": [cache_entry()]},
        project_scope={"project_key": "DCPM"},
        semantic_follow_up=True,
    )
    assert decision.action == "reuse"


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


def _single_squad_cache(squad="BE 1"):
    return build_cache_entry(
        intent="ANALYSIS",
        project_scope={"project_key": "DCPM"},
        results=[{
            "query_id": "dora_metrics_by_squad",
            "filters": {"project_key": "DCPM", "dcpsquad": squad},
            "rows": [{"dcpsquad": squad, "release_year": 2022}],
            "row_count": 1,
        }],
    )


def test_scope_widening_follow_up_does_not_reuse_a_single_squad_cache():
    """Regression: "make the same for each squad" after a one-squad answer
    was served from that squad's cached rows, so the assistant reported
    metrics for BE 1 and claimed the other 20 squads had no data. They did --
    it simply never queried them."""

    memory = {"query_cache": [_single_squad_cache()]}
    for message in ["make the same for each squad", "make for all squad",
                    "compare the squads"]:
        decision = choose_cache_action(
            message, memory=memory, project_scope={"project_key": "DCPM"},
            semantic_follow_up=True,
        )
        assert decision.action == "none", message
        assert decision.reason == "scope_widened"


def test_asking_about_a_different_squad_forces_a_fresh_query():
    memory = {"query_cache": [_single_squad_cache()]}
    decision = choose_cache_action(
        "Kaiju team", memory=memory, project_scope={"project_key": "DCPM"},
        semantic_follow_up=True,
    )
    assert decision.action == "none"
    assert decision.reason == "different_squad_requested"


def test_genuine_follow_ups_still_reuse_the_cache():
    """The narrowing must not break ordinary follow-ups."""

    memory = {"query_cache": [_single_squad_cache()]}
    for message in ["why is that", "explain that"]:
        decision = choose_cache_action(
            message, memory=memory, project_scope={"project_key": "DCPM"},
            semantic_follow_up=True,
        )
        assert decision.action == "reuse", message
