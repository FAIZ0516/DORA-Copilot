"""FastAPI entry point for the DoraDB-only conversational AI application.

This module only creates the app, configures middleware/lifespan, and
includes the routers defined in ``backend/api/``. Request handling itself
lives there, one router per resource area -- see AGENTS.md Section 4.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import ROUTERS
from .config import settings
from .database.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialize the writable runtime store; analytical DoraDB remains read-only.
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "DeepSeek-powered conversational DORA intelligence over the real, "
        "read-only PostgreSQL DoraDB dataset."
    ),
    version="0.4.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_pattern,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "X-Development-Session"],
)

for router in ROUTERS:
    app.include_router(router)
