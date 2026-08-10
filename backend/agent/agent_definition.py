"""Runtime agent definition: the one place the DoraDB agent is configured
(guide Section 9).

Creates/configures the agent, loads permanent instructions (via the
responder, which reads ``INSTRUCTIONS.md``/skills on every turn), registers
the tool/guardrail/validator-backed graph nodes, configures the model
provider, and attaches runtime context. Business logic is deliberately not
here: node behavior lives in ``orchestrator.py`` (``AgentOrchestrator``
mixin), and answer composition lives in ``response/responder.py``.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from ..config import settings
from ..database.doradb import DoraDbQueryRejected
from ..llm import GenerativeAIClient
from .context import RuntimeContext
from .orchestrator import AgentOrchestrator
from .response.responder import Responder
from .state import AgentState


class AdvancedDoraDbAgent(AgentOrchestrator):
    """A generative agent with deterministic controls around every data action."""

    def __init__(self, session: Session | None) -> None:
        self.session = session
        self.llm = GenerativeAIClient(settings)
        self.responder = Responder(self.llm)

        graph = StateGraph(AgentState)
        graph.add_node("load_memory", self._load_memory)
        graph.add_node("plan", self._plan)
        graph.add_node("execute", self._execute)
        graph.add_node("validate_result", self._validate_result)
        graph.add_node("repair", self._repair)
        graph.add_node("analyze", self._analyze)
        graph.add_node("respond", self.responder.respond)
        graph.add_node("validate_answer", self._validate_answer)
        graph.add_node("regenerate", self.responder.regenerate)
        graph.add_node("save", self._save)
        graph.set_entry_point("load_memory")
        graph.add_edge("load_memory", "plan")
        graph.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {"execute": "execute", "analyze": "analyze", "respond": "respond"},
        )
        graph.add_edge("execute", "validate_result")
        graph.add_conditional_edges(
            "validate_result",
            self._route_after_result_validation,
            {"repair": "repair", "analyze": "analyze"},
        )
        graph.add_edge("repair", "validate_result")
        graph.add_edge("analyze", "respond")
        graph.add_edge("respond", "validate_answer")
        graph.add_conditional_edges(
            "validate_answer",
            self._route_after_answer_validation,
            {"regenerate": "regenerate", "save": "save"},
        )
        graph.add_edge("regenerate", "validate_answer")
        graph.add_edge("save", END)
        self.graph = graph.compile()

    def chat(
        self,
        message: str,
        *,
        session_id: str,
        history: list[dict[str, str]] | None = None,
        persistent_context: dict[str, Any] | None = None,
        project_scope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = RuntimeContext(
            session_id=session_id,
            message=message,
            history=history or [],
            persistent_context=persistent_context or {},
            project_scope=project_scope or {},
            db_session=self.session,
        )
        result = self.graph.invoke(context.to_initial_state())
        return {
            "answer": result["answer"],
            "intent": result["plan"]["intent"],
            "metric": result.get("metric", {}).get("id"),
            "chart": result.get("chart"),
            "table": result.get("table"),
            "warnings": result.get("warnings", []),
            "validation": result.get("validation", {}),
            "metadata": result.get("metadata", {}),
            "_persistence": result.get("persistence", {}),
        }


__all__ = ["AdvancedDoraDbAgent", "DoraDbQueryRejected"]
