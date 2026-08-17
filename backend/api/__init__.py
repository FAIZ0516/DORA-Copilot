"""API layer: FastAPI routers. ``main.py`` only creates the app and includes
these; request handling itself lives here, one router per resource area."""

from . import (
    chat,
    conversations,
    dashboard,
    reports,
    role_dashboard,
    system,
    tts,
    voice,
    workspace,
)

ROUTERS = (
    conversations.router,
    chat.router,
    dashboard.router,
    reports.router,
    role_dashboard.router,
    system.router,
    tts.router,
    voice.router,
    workspace.router,
)

__all__ = ["ROUTERS"]
