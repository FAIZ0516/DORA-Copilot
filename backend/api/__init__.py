"""API layer: FastAPI routers. ``main.py`` only creates the app and includes
these; request handling itself lives here, one router per resource area."""

from . import chat, conversations, dashboard, system, tts

ROUTERS = (
    conversations.router,
    chat.router,
    dashboard.router,
    system.router,
    tts.router,
)

__all__ = ["ROUTERS"]
