"""Data access layer: isolates all database work from AI behavior.

``db.py`` is the writable runtime store (conversations, TTS usage).
``doradb.py`` + ``doradb_catalog.py`` are the read-only DoraDB engine and its
approved, parameterized query catalogue -- the AI model never constructs
arbitrary SQL; it only ever selects an approved query ID (see AGENTS.md
Section 9).
"""
