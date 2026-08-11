from unittest.mock import patch

from backend.agent.orchestrator import AgentOrchestrator
from backend.agent.response.responder import generate_follow_up_questions
from backend.services.entity_grounding import detect_squad_scope_mismatch


CATALOGUE = {"squad": ["TITAN", "JAEGER", "MBK"]}


def test_single_squad_scope_allows_same_squad_but_blocks_other_and_cross_squad():
    assert detect_squad_scope_mismatch(
        "How many open bugs does TITAN have?",
        active_squad="TITAN",
        catalogue=CATALOGUE,
    ) is None

    different = detect_squad_scope_mismatch(
        "How many open bugs does JAEGER have?",
        active_squad="TITAN",
        catalogue=CATALOGUE,
    )
    assert different is not None
    assert different["requested_squad"] == "JAEGER"
    assert different["available_actions"] == [
        "switch_to_requested_squad",
        "go_to_all_squads",
    ]

    cross = detect_squad_scope_mismatch(
        "Which squad has the most open bugs?",
        active_squad="TITAN",
        catalogue=CATALOGUE,
    )
    assert cross is not None
    assert cross["requested_squad"] is None


def test_all_squads_scope_allows_cross_squad_questions():
    assert detect_squad_scope_mismatch(
        "Rank all squads by open bugs.",
        active_squad=None,
        catalogue=CATALOGUE,
    ) is None


def test_orchestrator_blocks_scope_mismatch_before_planning_or_metric_query():
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    state = {
        "message": "Compare TITAN with JAEGER",
        "memory": {"dashboard_context": {"squad": "TITAN"}},
        "project_scope": {"project_key": "DCPM"},
        "db_session": object(),
    }
    with (
        patch("backend.agent.orchestrator.load_entity_catalogue", return_value=CATALOGUE),
        patch("backend.agent.orchestrator.create_plan") as planner,
    ):
        result = agent._plan(state)  # type: ignore[arg-type]

    planner.assert_not_called()
    assert result["plan"]["intent"] == "squad_scope_mismatch"
    assert result["plan"]["actions"] == []
    assert result["results"] == []
    assert result["database_query_executed"] is False


def test_dynamic_follow_ups_are_bounded_and_stay_in_active_scope():
    class FakeLlm:
        enabled = True

        @staticmethod
        def complete(*_args: object, **_kwargs: object) -> str:
            return (
                '{"suggestions":['
                '"Which TITAN statuses contribute most to the backlog?",'
                '"How does JAEGER compare with TITAN?",'
                '"Which TITAN priorities need attention?",'
                '"Show TITAN unresolved issue types."'
                "]}"
            )

    suggestions = generate_follow_up_questions(
        FakeLlm(),  # type: ignore[arg-type]
        question="Summarise TITAN delivery risk.",
        answer="TITAN has elevated open bugs.",
        dashboard_context={"squad": "TITAN", "project": "DCPM"},
        squads=CATALOGUE["squad"],
    )

    assert suggestions == [
        "Which TITAN statuses contribute most to the backlog?",
        "Which TITAN priorities need attention?",
        "Show TITAN unresolved issue types.",
    ]
