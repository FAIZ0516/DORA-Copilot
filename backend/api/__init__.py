"""API layer: FastAPI routers. ``main.py`` only creates the app and includes
these; request handling itself lives here, one router per resource area."""

from . import chat, conversations, dashboard, role_dashboard, system, tts, workspace

ROUTERS = (
    conversations.router,
    chat.router,
    dashboard.router,
    role_dashboard.router,
    system.router,
    tts.router,
    workspace.router,
)

__all__ = ["ROUTERS"]
