# How to Implement AGENTS.md (Project Instructions) and SKILL.md (Custom Skills) in OpenAI Codex

> **Source:** User-provided implementation guide.
> **Date captured:** 2026-08-05

---

## 1. Project / Global Instructions — `AGENTS.md`

Project or global instructions give Codex the big-picture context, preferred tools, and rules it must remember across all sessions in a repository.

### Steps

1. **Create a file named `AGENTS.md`** in the root directory of your project (or globally in your user profile home folder).
2. **Write your core project guidelines** in plain text or markdown. Include coding standards, frameworks used, and constraints.
   - Example Rule: *Prefer composition over inheritance in all UI components.*
   - Example Rule: *Never commit a change directly to the generated production schema file.*
3. **Save the file.** Codex automatically detects and loads `AGENTS.md` at the start of every session.

---

## 2. Custom Skills — `SKILL.md`

Skills act as reusable workflow recipe cards that expand via **progressive disclosure** only when triggered, saving context tokens.

### Steps

1. **Create a dedicated folder** for your skill inside your project (`.codex/skills/<skill-name>/`) or globally (`~/.codex/skills/<skill-name>/`).
2. **Inside that folder, create a `SKILL.md` file.**
3. **Add mandatory YAML frontmatter** containing the `name` and `description`, followed by the specific task instructions:

   ```markdown
   ---
   name: doc-api
   description: Scans views, URLs, and serializers to output a frontend-friendly markdown API reference file.
   ---
   # Instructions for doc-api
   1. Scan all active router URLs and Django view files.
   2. Extract endpoint URLs, request parameters, and response structures.
   3. Output the result into `api-docs.md` at the root directory.
   ```

4. **(Optional)** Configure invocation behavior by creating an `agents/openai.yaml` file in the same directory if you want to restrict or allow implicit vs. explicit execution.
5. **Restart or reload Codex** so it reindexes the new metadata list.

---

## 3. Invoking and Managing Skills

| Method | How |
|---|---|
| **Explicit Invocation** | Type `$` followed by the skill name (e.g., `$doc-api`) directly in your prompt or CLI chat. |
| **Implicit Invocation** | Codex will automatically trigger the skill if your natural language request matches the description defined in `SKILL.md`. |
| **Interactive Creator** | Use the built-in `$skill-creator` command inside an active Codex chat to let the agent package your current prompt workflow into a structured skill file automatically. |

---

## 4. File Tree Summary

```
project-root/
├── AGENTS.md                          # ← Project-wide instructions (auto-loaded every session)
└── .codex/
    └── skills/
        └── <skill-name>/
            ├── SKILL.md               # ← Skill definition (YAML frontmatter + instructions)
            └── agents/
                └── openai.yaml        # ← (Optional) invocation behavior config
```

For global (cross-project) use, place the same structure under `~/.codex/` instead.
