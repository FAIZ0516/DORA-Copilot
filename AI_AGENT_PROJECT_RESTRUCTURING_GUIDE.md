# AI Agent Project Restructuring Guide

> **Purpose:** This document is a restructuring specification for an existing AI-agent application.  
> It is intentionally **architecture-first and implementation-agnostic**.  
> The coding agent MUST inspect the current repository before creating, moving, renaming, or deleting files.
>
> **Primary rule:** Do not create a file, folder, agent, skill, tool, guardrail, validator, or service merely because it appears in an example structure below. Create or split a component only when the responsibility exists and is not already handled cleanly by the current codebase.

---

## 1. Goals

Restructure the project so that these concerns are clearly separated:

1. **AI IDE instructions and development skills**
2. **Runtime AI agent instructions**
3. **Runtime task-specific skills**
4. **Conversation and response control**
5. **Planning / routing / orchestration**
6. **Tools and external capabilities**
7. **Business/domain logic**
8. **Data access**
9. **Guardrails and permissions**
10. **Validation and evidence checking**
11. **Conversation state / memory**
12. **Testing and agent evaluation**
13. **Tracing / observability**
14. **Optional integrations such as MCP**

The final design must remain as simple as the current product allows.

---

# 2. Non-Negotiable Restructuring Rules

Before changing the project, the AI IDE MUST:

1. Inspect the repository structure.
2. Identify the framework, runtime, database layer, model provider, and current agent flow.
3. Find existing files that already perform the responsibilities described in this document.
4. Produce a mapping:

```text
Existing component
→ Current responsibility
→ Target responsibility
→ Keep / rename / move / split / remove
→ Reason
```

5. Prefer **reusing and improving existing modules** over creating parallel replacements.
6. Do not create duplicate implementations of:
   - agent runners;
   - prompt loaders;
   - session managers;
   - tool registries;
   - database connections;
   - repositories;
   - guardrails;
   - validators;
   - API clients;
   - response formatters.
7. Preserve working behavior unless there is a documented reason to change it.
8. Add or update tests when behavior changes.
9. Do not introduce MCP, multi-agent orchestration, vector databases, queues, extra frameworks, or additional abstraction layers unless the current requirements justify them.
10. Prefer one clear implementation over multiple competing patterns.
11. Keep security and deterministic validation in code rather than relying only on prompt instructions.
12. Treat examples in this file as **responsibility models**, not mandatory filenames.

---

# 3. Source-Backed Facts vs Architecture Recommendations

This document distinguishes between:

## 3.1 Source-backed OpenAI / Codex behavior

The following are current documented behaviors:

- Codex reads applicable `AGENTS.md` files before doing work.
- Repository-scoped Codex skills can live under `.agents/skills`.
- A Codex skill is a directory containing a required `SKILL.md`.
- Codex skills use progressive disclosure: name/description are exposed first; full `SKILL.md` is loaded when selected.
- Skill scripts, references, and assets are optional.
- OpenAI Agents SDK supports:
  - agent instructions;
  - function tools;
  - runtime context;
  - sessions / conversation state;
  - input, output, and tool guardrails;
  - structured output;
  - tracing;
  - MCP integration.

## 3.2 Project architecture recommendations

The following names are **recommended project organization**, not OpenAI requirements:

- `planner.py`
- `orchestrator.py`
- `response_controller.py`
- `skill_registry.py`
- `skill_loader.py`
- `services/`
- `repositories/`
- `validators/`
- `controls/`
- `response/`

The coding agent may map these responsibilities onto existing equivalents.

---

# 4. Target Conceptual Architecture

A mature version of the application should conceptually look like this:

```text
User
  ↓
API / Chat Interface
  ↓
Runtime Agent
  ↓
Input Guardrails
  ↓
Conversation Context
  ↓
Planner / Intent Router
  ↓
Runtime Skill Selection
  ↓
Approved Tools
  ↓
Services / Domain Logic
  ↓
Repositories / External Data
  ↓
Data + Metric Validation
  ↓
Response Controller
  ↓
Responder
  ↓
Output / Evidence Validation
  ↓
User
```

This flow is conceptual. Do not create one module for every arrow unless needed.

---

# 5. Suggested Repository Shape

Use this as a reference, not a mandatory tree.

```text
PROJECT_ROOT/
│
├── AGENTS.md
│
├── .agents/
│   └── skills/
│       └── <development-skill>/
│           └── SKILL.md
│
├── frontend/
│   └── ...
│
├── backend/
│   ├── main.py
│   ├── config.py
│   │
│   ├── api/
│   │   └── ...
│   │
│   ├── agent/
│   │   ├── INSTRUCTIONS.md
│   │   ├── instruction_loader.py
│   │   ├── agent_definition.py
│   │   ├── context.py
│   │   ├── orchestrator.py
│   │   ├── planner.py
│   │   │
│   │   ├── controls/
│   │   │   ├── response_controller.py
│   │   │   ├── execution_control.py
│   │   │   └── permission_control.py
│   │   │
│   │   ├── guardrails/
│   │   │   ├── input_guardrail.py
│   │   │   ├── tool_guardrail.py
│   │   │   └── output_guardrail.py
│   │   │
│   │   ├── validators/
│   │   │   ├── request_validator.py
│   │   │   ├── data_validator.py
│   │   │   ├── metric_validator.py
│   │   │   ├── evidence_validator.py
│   │   │   └── response_validator.py
│   │   │
│   │   ├── response/
│   │   │   ├── responder.py
│   │   │   └── response_models.py
│   │   │
│   │   └── skills/
│   │       └── <runtime-skill>/
│   │           ├── SKILL.md
│   │           └── handler.py
│   │
│   ├── tools/
│   │   └── ...
│   │
│   ├── services/
│   │   └── ...
│   │
│   ├── database/
│   │   └── ...
│   │
│   └── memory/
│       └── ...
│
├── tests/
│   ├── unit/
│   └── integration/
│
└── evals/
    └── ...
```

### Important

If the existing project is small, it is acceptable to combine:

```text
controls + guardrails + validators
```

into a smaller number of modules initially.

Split them only when:

- the file has multiple unrelated responsibilities;
- different behaviors need different tests;
- ownership becomes unclear;
- changes regularly interfere with one another.

---

# 6. AI IDE Layer

## 6.1 `AGENTS.md`

### Purpose

`AGENTS.md` is for the coding AI / Codex.

It should describe durable repository-wide development rules such as:

- project purpose;
- repository layout;
- technology stack;
- important commands;
- build/test/lint procedures;
- architecture boundaries;
- coding conventions;
- security expectations;
- definition of done;
- how to verify changes;
- what the coding agent must not modify without reason.

### It should NOT be used as

- the runtime system prompt for the product's internal AI;
- a replacement for application security;
- a replacement for tests;
- a database schema dump;
- a place for every task-specific workflow.

### Keep it durable

Rules that apply only to a narrow/repetitive workflow belong in a Codex skill rather than making `AGENTS.md` unnecessarily large.

---

# 7. AI IDE Development Skills

Repository-scoped Codex skills should use the documented repository skill location:

```text
.agents/
└── skills/
    └── <skill-name>/
        └── SKILL.md
```

A development skill should represent a reusable development workflow.

Examples:

```text
create-runtime-skill
test-agent-behaviour
add-api-endpoint
database-migration
security-review
```

Do NOT create a skill for every ordinary coding task.

## Skill creation rule

Create a Codex skill when:

- the workflow is repeated;
- it has a clear trigger;
- it benefits from a fixed sequence;
- it has specific validation steps;
- it contains domain-specific knowledge Codex should reuse.

Instruction-only should be preferred unless deterministic scripts or external tooling are genuinely needed.

---

# 8. Runtime Internal AI Instructions

## 8.1 Prefer one main instruction file initially

A single file is sufficient:

```text
backend/agent/INSTRUCTIONS.md
```

The project does not need separate files such as:

```text
safety_rules.md
data_rules.md
response_rules.md
analysis_rules.md
```

unless the instruction file becomes too large or different teams own different policies.

## 8.2 Recommended sections inside `INSTRUCTIONS.md`

```text
1. Identity and role
2. Product purpose
3. Data-use rules
4. Analysis principles
5. Tool-use principles
6. Safety/privacy principles
7. Evidence principles
8. High-level response behavior
9. Failure / missing-data behavior
10. Out-of-scope behavior
```

## 8.3 What should stay out of the instruction file

Do not rely only on prompt text for:

- authentication;
- authorization;
- database write restrictions;
- input schema validation;
- calculation validation;
- rate limits;
- tool allowlists;
- confidential-data enforcement;
- audit logging.

Those require code-level enforcement.

---

# 9. Runtime Agent Definition

There should be one clear place where the runtime AI agent is configured.

Possible names:

```text
agent_definition.py
zara_agent.py
runtime_agent.py
```

Use whichever best matches the existing project.

Responsibilities:

- create/configure the agent;
- load permanent instructions;
- register allowed tools;
- register guardrails;
- configure model/provider;
- configure output type where appropriate;
- attach runtime context;
- attach MCP only when used;
- avoid business logic in the agent-definition file.

---

# 10. Runtime Context

Context is application-owned state that should not be manually stuffed into every prompt.

Typical context may include:

```text
user_id
role
permissions
allowed_data_scope
session_id
database/service handles
request metadata
tenant/business unit
current reporting scope
feature flags
```

Context should support tools and policies without exposing unnecessary internal data to the model.

Do not create a custom context abstraction if the framework already provides an equivalent mechanism.

---

# 11. Planner / Intent Router

A planner is optional.

Use a dedicated planner only if the product genuinely needs:

- intent classification;
- runtime skill selection;
- multi-step task routing;
- deterministic routing rules;
- different workflows for different request types.

Avoid creating a planner that micromanages every tool call when the runtime agent can already select tools safely.

Recommended responsibility:

```text
User request
→ identify intent
→ extract important entities/constraints
→ choose relevant runtime skill/workflow
```

Not:

```text
choose every function
choose every SQL statement
choose every validator
choose every sentence format
```

---

# 12. Runtime Skills

Runtime product skills are different from Codex development skills.

Example concept:

```text
backend/agent/skills/
└── productivity-analysis/
    ├── SKILL.md
    └── handler.py
```

These are application-defined unless the runtime explicitly uses a native skill mechanism.

## A runtime skill should answer

- What task does this skill solve?
- When should it be selected?
- When should it NOT be selected?
- What inputs are required?
- Which tools/data are allowed?
- What workflow should be followed?
- What deterministic checks are required?
- What result should be returned?
- What should happen if data is missing?

## `SKILL.md`

Use it for:

- workflow instructions;
- domain interpretation rules;
- tool-selection guidance;
- expected inputs/outputs;
- edge cases;
- analysis boundaries.

## `handler.py`

Use it only if code-backed orchestration is needed.

Do not create a handler if the skill is entirely instruction-based and the runtime can execute it safely without one.

---

# 13. Skill Registry / Skill Loader

A custom runtime `skill_registry` and `skill_loader` are only needed if the application uses its own runtime skill system.

They are NOT required merely because Codex uses skills.

Use them when the application must:

- discover local runtime skills;
- map intent → skill;
- selectively load `SKILL.md`;
- validate skill metadata;
- expose a controlled skill set.

Do not add them if the current runtime framework already supplies equivalent native functionality.

---

# 14. Tools Layer

Tools are the capabilities the model is permitted to call.

Examples:

```text
get_squad_metrics
compare_periods
retrieve_issues
get_delivery_risk
generate_report_data
```

Tools should:

- have narrow responsibilities;
- use explicit typed inputs;
- validate arguments;
- return structured outputs when practical;
- call services rather than containing large business logic;
- avoid direct unrestricted SQL;
- expose only the minimum capability needed.

Recommended conceptual path:

```text
Agent
→ Tool
→ Service
→ Repository/API
```

Avoid:

```text
Agent
→ arbitrary SQL
```

---

# 15. Services / Domain Logic

Services contain reusable business logic.

Examples:

```text
metric_service
jira_service
report_service
risk_service
```

Place here:

- business calculations;
- aggregation;
- comparison logic;
- workflow logic shared by multiple tools;
- domain transformations.

Do not duplicate the same calculation in:

- a prompt;
- a tool;
- a skill handler;
- a frontend component.

There should be one authoritative deterministic implementation.

---

# 16. Repository / Data Access Layer

Repositories or data-access modules should isolate database queries from AI behavior.

Responsibilities may include:

- issue retrieval;
- sprint retrieval;
- squad retrieval;
- reporting-period queries;
- database filtering;
- pagination;
- mapping database records to domain structures.

The AI model should not be responsible for constructing arbitrary destructive queries.

If direct text-to-SQL is intentionally supported, it must have explicit scope, validation, permissions, and read/write restrictions.

---

# 17. Guardrails

Guardrails are for **checking, blocking, rejecting, or constraining unsafe/invalid behavior**.

Keep them conceptually separate from response style.

## 17.1 Input guardrails

Possible responsibilities:

- prompt injection detection;
- restricted request checks;
- prohibited data request detection;
- scope validation;
- unsafe input detection.

## 17.2 Tool guardrails

Possible responsibilities:

- validate tool arguments;
- block disallowed tool calls;
- enforce data scopes;
- block unsafe query parameters;
- check permissions before execution;
- validate tool outputs where needed.

## 17.3 Output guardrails

Possible responsibilities:

- sensitive-data leakage;
- unsupported claims;
- restricted information;
- policy violations;
- output safety.

### Important principle

A sentence in `INSTRUCTIONS.md` such as:

```text
Never expose confidential data.
```

is useful guidance, but it is not equivalent to code-level access control.

---

# 18. Controls

Controls determine **how the agent is allowed to operate and how it should interact**.

Separate controls into two conceptual groups:

```text
CONTROLS
├── Execution Control
└── Response Controller
```

---

# 19. Execution Control

Execution control covers operational limits.

Possible responsibilities:

- allowed tools;
- tool-call limits;
- retry limits;
- timeouts;
- token/cost limits;
- model selection policy;
- user permissions;
- data scope;
- approval requirements;
- read/write restrictions;
- rate limits.

Do not put response tone or formatting logic in execution control.

---

# 20. Response Controller

The Response Controller is responsible for **how the AI communicates with the user**.

It is NOT primarily a safety system.

The response controller should derive a per-turn response policy from:

```text
current user message
+ conversation state
+ detected follow-up type
+ user-requested format
+ task type
+ evidence availability
+ result complexity
+ application defaults
```

It should then provide guidance to the responder/agent.

Conceptually:

```text
User message
      ↓
Conversation state
      ↓
Response Controller
      ↓
Response Policy
      ↓
Responder
```

Example response-policy object:

```text
tone
length
format
explanation_level
language
is_follow_up
follow_up_type
context_reference
evidence_style
uncertainty_mode
recommendation_mode
priority_order
suggest_next_action
```

The exact implementation can be a class, dataclass, Pydantic model, dictionary, or existing equivalent.

---

# 21. Response Controller Requirements

The Response Controller should cover the following behavior.

## 21.1 Style

### Tone

Control whether the response should be:

- professional;
- neutral;
- friendly;
- concise;
- analytical;
- executive-facing;
- technical.

Rules:

- use a consistent product personality;
- do not make tone changes randomly between turns;
- explicit user tone requests override defaults unless unsafe/inappropriate.

### Answer Length

Support at least:

```text
short
normal
detailed
```

Behavior:

- simple factual question → short;
- explanation / comparison → normal;
- explicit deep explanation → detailed;
- follow-up asking "why?" should expand only the relevant part rather than repeating everything.

### Answer Format

Choose the format based on task shape, not habit.

Examples:

```text
paragraph
bullets
numbered steps
table
structured sections
chart-ready response
```

Guidance:

- short explanation → paragraph;
- multiple independent points → bullets;
- ordered procedure → numbered steps;
- comparison across consistent attributes → table;
- quantitative trend where visualization materially helps → chart or chart-ready data.

Do not force bullet points for every answer.

### Explanation Level

Support levels such as:

```text
layman
standard
technical
executive
```

Use explicit user preference when stated.

Otherwise infer from the current request and recent conversation.

---

# 22. Conversation Behavior

## 22.1 Follow-Up Understanding

The agent must treat short follow-ups as part of the current conversation when context makes their meaning clear.

Examples:

```text
"why?"
"how?"
"what about Squad B?"
"and last month?"
"which one?"
"can it do that?"
```

Do not require the user to repeat the full question when the referent can be resolved reliably.

## 22.2 Reference Previous Answer

When a follow-up clearly refers to a previous result:

- reuse the relevant prior conclusion;
- do not recompute unless the data/time scope changed or verification is required;
- mention the previous result only as much as needed.

## 22.3 Follow-Up Type Detection

Recognize categories such as:

```text
clarification
deeper explanation
comparison extension
scope change
time-period change
format change
correction
challenge / verification
new question
action request
```

A follow-up detector may be deterministic, model-based, or integrated into the planner.

Do not create a separate classifier unless it improves reliability.

## 22.4 Keep Existing Context

Preserve constraints that remain active, such as:

```text
selected squad
selected sprint
reporting period
comparison target
preferred output style
user role
previously resolved entity
```

Do not preserve constraints that the user explicitly replaces.

## 22.5 Resolve Pronouns and Short References

Resolve terms such as:

```text
it
that
this
they
them
the first one
the second one
why
how
```

from recent conversation context.

If there are multiple plausible referents with materially different answers, clarify.

---

# 23. Clarification Behavior

Ask a clarification only when missing information materially changes the result and cannot be safely inferred from:

- conversation state;
- application context;
- available data;
- reasonable defaults.

Do NOT ask unnecessary clarification when:

- the answer is obvious from context;
- a sensible default is low-risk;
- the user is asking a simple follow-up;
- available tools can resolve the ambiguity.

When clarification is needed:

- ask the minimum question required;
- explain choices only if helpful;
- avoid making the user restate known information.

---

# 24. Direct-Answer Behavior

Default pattern:

```text
Answer first
→ explanation/evidence second
→ optional next action last
```

Avoid:

- long preambles;
- repeating the user's question;
- unnecessary definitions before answering;
- hiding the conclusion at the end.

For analytical questions:

```text
Finding
→ evidence
→ interpretation
→ recommendation
```

---

# 25. Progressive Detail

Responses should provide detail progressively.

Example:

```text
1. Direct conclusion
2. Key supporting evidence
3. Explanation
4. Deeper technical detail only when useful/requested
```

Follow-up questions should expand the requested section instead of repeating the complete previous answer.

---

# 26. Evidence Style

Evidence should be proportional to the claim.

Possible evidence levels:

```text
none_required
brief_support
metric_support
detailed_evidence
source_reference
```

Examples:

- casual greeting → no evidence;
- simple database fact → supporting value;
- performance conclusion → relevant metrics;
- recommendation → evidence + reasoning;
- uncertain interpretation → evidence + explicit uncertainty.

When data comes from application tools, prefer concrete values over vague phrases.

Bad:

```text
Performance seems worse.
```

Better:

```text
Completion fell from 82% to 68%, while average cycle time increased from 4.1 to 5.6 days.
```

---

# 27. Fact vs Interpretation

The response controller/responder must distinguish:

```text
FACT
Directly supported by retrieved/calculated data.

INTERPRETATION
A reasonable explanation inferred from facts.

RECOMMENDATION
A proposed action based on evidence and context.
```

Do not present interpretations as facts.

Useful language:

```text
"The data shows..."
"This may indicate..."
"A possible contributor is..."
"Based on these metrics, I recommend..."
```

---

# 28. Uncertainty Behavior

When confidence is limited:

- identify what is known;
- identify what is missing;
- state the effect of the missing information;
- avoid invented precision;
- do not fabricate data;
- suggest the smallest useful next step when appropriate.

Example pattern:

```text
The data confirms X.
It does not include Y, so the cause of Z cannot be established confidently.
A useful next check would be ...
```

Do not overuse uncertainty disclaimers when the evidence is clear.

---

# 29. Recommendation Behavior

Recommendations should:

- follow from evidence;
- be practical;
- be proportionate to confidence;
- distinguish immediate actions from longer-term improvements when useful;
- avoid generic recommendations that could apply to any result.

If evidence is insufficient, recommend investigation rather than pretending to know the solution.

---

# 30. Comparison Response

When the user compares entities:

1. define the comparison scope;
2. use consistent metrics;
3. present the most decision-relevant difference first;
4. use a table when several comparable dimensions exist;
5. explain why the difference matters;
6. avoid declaring an overall "winner" if metrics conflict unless a decision criterion is defined.

---

# 31. Priority Ordering

Order response content by:

```text
1. What answers the user's question
2. What has the highest decision impact
3. Strongest evidence
4. Important risks/limitations
5. Secondary detail
6. Optional next steps
```

Do not order content merely by the order in which data was retrieved.

---

# 32. Avoid Repetition

The agent should not:

- restate the entire previous answer on every follow-up;
- repeat the same caveat multiple times;
- repeat a metric in several sections without reason;
- restate user instructions that are already understood.

For follow-ups, answer the new information need.

---

# 33. User Correction Behavior

When a user corrects the agent:

1. accept the corrected fact/constraint when appropriate;
2. update conversation state;
3. revise the affected part;
4. do not defend the old answer unnecessarily;
5. do not repeat the original mistake;
6. recompute dependent results if required.

If the correction conflicts with trusted source data, explain the conflict and verify rather than silently accepting it.

---

# 34. Change-Format Behavior

If the user says:

```text
"make it shorter"
"put it in table"
"explain in paragraph"
"give only the answer"
"make it technical"
```

change the presentation while preserving the underlying conclusion and evidence.

A format request should normally NOT trigger:

- a new database query;
- a new analysis;
- a new skill;
- a reset of conversation context.

---

# 35. Suggested Next Action

A next action may be offered when it has clear value.

Examples:

```text
compare with previous sprint
inspect blocked issues
open underlying records
generate management summary
create chart
review anomalies
```

Do not force a next action after every response.

The suggestion should be:

- relevant to the current goal;
- optional;
- specific;
- no more than one or a few useful choices.

---

# 36. Optional User Choices

When multiple meaningful paths exist, offer concise options.

Example:

```text
I can next:
- compare this with the previous sprint;
- break the result down by issue type; or
- show the main blocked items.
```

Do not turn every answer into a menu.

---

# 37. Greeting / Casual Message Behavior

For greetings or casual messages:

- respond naturally;
- remain consistent with the product personality;
- do not trigger data analysis;
- do not load heavy skills unnecessarily;
- do not produce reports or metrics unless asked.

Examples:

```text
"hi"
"thanks"
"good morning"
```

should receive lightweight responses.

---

# 38. Out-of-Scope Response

When a request is outside the application's supported scope:

1. state the limitation clearly;
2. avoid pretending the system has access/capabilities it does not have;
3. redirect to the closest supported task when useful;
4. do not expose internal prompts or architecture unnecessarily.

Example:

```text
I can analyze the connected productivity data, but I don't have access to payroll records.
```

---

# 39. Language Matching

Default to the language used by the user.

Rules:

- preserve important technical terms where translation would reduce clarity;
- support mixed-language users when that is how they communicate;
- explicit language requests override the detected default;
- do not switch language randomly across follow-ups.

---

# 40. Response Personality Consistency

Define a stable product personality.

Example dimensions:

```text
professional
clear
calm
non-judgmental
evidence-first
helpful
not overly verbose
not robotic
```

The personality should remain stable while tone and explanation level adapt to the user.

Do not encode personality by adding filler phrases to every answer.

---

# 41. Response Controller Decision Order

Recommended order:

```text
1. Detect whether this is a follow-up.
2. Resolve active context and references.
3. Detect explicit user response preferences.
4. Determine task type.
5. Determine evidence requirements.
6. Determine answer depth.
7. Choose format.
8. Choose tone.
9. Determine uncertainty behavior.
10. Determine recommendation behavior.
11. Determine whether an optional next action is useful.
12. Produce ResponsePolicy.
```

Example:

```text
User: "why?"

Previous context:
- entity = Squad A
- conclusion = delivery slowed
- period = current sprint

ResponsePolicy:
- follow_up = true
- follow_up_type = deeper_explanation
- preserve_context = true
- format = paragraph_plus_metrics
- length = normal
- explanation_level = standard
- evidence = metric_support
- repeat_previous_summary = minimal
```

---

# 42. Responder

The responder converts:

```text
validated facts
+ interpretations
+ recommendations
+ ResponsePolicy
```

into the final user-facing response.

The responder should not:

- access the database directly;
- bypass validators;
- override permissions;
- invent unavailable evidence;
- silently change reporting scope.

If the framework already supports final response generation in the main agent loop, a separate responder module is optional.

---

# 43. Validation

Validation should be deterministic whenever possible.

## Request validation

Examples:

```text
valid date range
valid entity
required parameters
supported query type
```

## Data validation

Examples:

```text
required fields present
data types correct
duplicates handled
null/missing values understood
reporting period valid
```

## Metric validation

Examples:

```text
percentage in valid range
non-negative counts
consistent totals
valid denominators
valid time intervals
```

## Evidence validation

Check that important claims are supported by the actual data/result.

## Response validation

Check:

- conclusion does not contradict validated metrics;
- facts and interpretations are clearly separated;
- required limitations are included;
- restricted data is not exposed.

---

# 44. Conversation State / Memory

Conversation state is needed when the product supports multi-turn chat.

Store only what is needed.

Possible state:

```text
conversation/session identifier
recent relevant turns
active entity
active period
active filters
previous result references
user-requested response preferences
pending clarification
```

Avoid treating conversational memory as a substitute for the source database.

When the latest data matters, query the source of truth rather than trusting an old conversational value.

---

# 45. Testing

Normal software tests should verify deterministic behavior.

Examples:

```text
tool input validation
permission rules
metric calculations
repository queries
response policy selection
follow-up detection
format selection
language selection
```

Important Response Controller tests should include:

```text
simple question → short/direct
"why?" follow-up → preserve previous context
"make it a table" → change format only
user correction → replace affected context
comparison → table when appropriate
uncertain data → explicit uncertainty
casual greeting → no heavy tool call
out-of-scope → concise limitation
Malay user message → Malay response when appropriate
```

---

# 46. Agent Evaluation

Tests prove code correctness.

Agent evals measure AI behavior quality.

Evaluate at least:

```text
intent/skill selection
tool selection
context retention
follow-up resolution
factual accuracy
evidence grounding
hallucination rate
uncertainty calibration
recommendation relevance
format compliance
response length compliance
language matching
repetition
correction handling
```

Create a stable evaluation dataset containing representative user questions and expected properties.

Do not evaluate only exact wording.

---

# 47. Tracing / Observability

Use existing framework tracing when available before building a custom observability platform.

Important events to inspect:

```text
agent run
model call
tool call
tool result
guardrail result
selected skill
validation failure
response policy
final answer
token/usage information
```

Add custom logging only for information not already available.

Never log confidential payloads by default.

---

# 48. MCP

MCP is optional.

Add MCP only when it solves a real integration problem, such as:

- the same tools must be reused by multiple AI clients;
- tools live in a separate process/system;
- standardized tool/resource discovery is valuable;
- private or remote capability boundaries need an MCP interface.

Do not add MCP only because the application contains an AI agent.

Without MCP:

```text
Agent
→ Function Tool
→ Service
→ Database/API
```

With MCP:

```text
Agent
→ MCP Client
→ MCP Server Tool
→ Service
→ Database/API
```

MCP does not replace:

- instructions;
- skills;
- guardrails;
- permissions;
- validation;
- business logic;
- response control.

If MCP is added later, preserve the service/domain layer so function tools and MCP tools can reuse the same business logic.

---

# 49. Configuration and Secrets

Keep configuration separate from code.

Typical configuration:

```text
model/provider
database URL
feature flags
tool limits
timeouts
environment
logging level
```

Secrets must not be committed.

Use environment variables or the project's approved secret-management system.

Keep `.env.example` free of real credentials.

---

# 50. Definition of Done for Restructuring

The restructuring is complete only when:

- existing behavior is preserved or documented changes are intentional;
- there is one clear runtime agent entry/configuration;
- permanent runtime instructions have one clear source;
- AI IDE instructions and runtime AI instructions are not confused;
- Codex development skills and runtime product skills are clearly separated;
- tools have clear boundaries;
- business logic is not duplicated across prompts/tools/UI;
- permissions are enforced in code;
- guardrails exist where needed;
- validators cover critical metrics/data;
- conversation context is preserved correctly;
- response behavior is controlled consistently;
- tests pass;
- representative agent evals pass;
- no obsolete duplicate modules remain;
- documentation reflects the final architecture.

---

# 51. Restructuring Procedure for the AI IDE

The coding agent should follow this sequence.

## Phase 1 — Inspect

Do not modify code yet.

Identify:

```text
entry points
agent creation
model calls
prompt/instruction files
tool definitions
database queries
business calculations
conversation storage
response formatting
permissions
validation
tests
```

## Phase 2 — Map

Create a responsibility map from existing code to this document.

Example:

```text
existing chat_service.py
→ currently: prompt construction + DB call + response formatting
→ target:
   prompt construction → agent/instruction handling
   DB call → tool/service/repository
   response formatting → response controller/responder
```

## Phase 3 — Identify real problems

Only restructure when there is a reason such as:

```text
mixed responsibilities
duplicate logic
unsafe model access
unclear data boundaries
unmaintainable prompt code
missing validation
missing conversation state
inconsistent responses
untestable behavior
```

## Phase 4 — Design minimal changes

Prefer the smallest architecture that achieves clear separation.

## Phase 5 — Implement incrementally

Change one responsibility at a time.

Run tests after each meaningful change.

## Phase 6 — Remove obsolete paths

After replacement is verified:

- remove dead code;
- remove unused prompt files;
- remove duplicate tool implementations;
- remove old imports;
- update docs.

## Phase 7 — Evaluate behavior

Run representative multi-turn scenarios, not only unit tests.

---

# 52. Anti-Patterns to Avoid

Do not restructure into:

```text
one file per tiny function
one agent per question type
one skill per user phrase
one validator per field
one MCP server per tool
one prompt file per rule
```

Avoid:

- speculative abstractions;
- empty folders;
- placeholder modules with no real responsibility;
- duplicated rules in multiple layers;
- business calculations only in prompts;
- security enforced only by instructions;
- arbitrary SQL generated and executed without control;
- response styling mixed into safety guardrails;
- tool logic mixed into frontend code;
- conversation history treated as authoritative business data.

---

# 53. Practical Minimum Architecture

If the current application is still small, the minimum acceptable structure may simply be:

```text
PROJECT_ROOT/
├── AGENTS.md
├── .agents/
│   └── skills/
│
└── backend/
    ├── main.py
    ├── agent/
    │   ├── INSTRUCTIONS.md
    │   ├── agent_definition.py
    │   ├── orchestrator.py
    │   ├── response_controller.py
    │   └── skills/
    ├── tools.py
    ├── services.py
    ├── protections.py
    └── database.py
```

This is acceptable if responsibilities are clear and tests exist.

Only split it further as complexity grows.

---

# 54. Practical Expanded Architecture

When the project becomes large enough, evolve toward:

```text
backend/
├── agent/
│   ├── INSTRUCTIONS.md
│   ├── agent_definition.py
│   ├── context.py
│   ├── orchestrator.py
│   ├── planner.py
│   ├── controls/
│   ├── guardrails/
│   ├── validators/
│   ├── response/
│   └── skills/
├── tools/
├── services/
├── database/
└── memory/
```

The trigger for expansion is complexity, not aesthetics.

---

# 55. Source References

The architecture above is grounded in current official OpenAI/Codex documentation, while project-specific folder names and separation choices are explicitly recommendations.

Verified: **2026-08-09**

## Codex — AGENTS.md

Official documentation:

https://developers.openai.com/codex/agent-configuration/agents-md

Key documented points:

- Codex reads `AGENTS.md` before doing work.
- Project instructions can be layered by directory.
- Repository-level instructions should contain durable project guidance.

## Codex — Skills

Official documentation:

https://developers.openai.com/codex/build-skills

Key documented points:

- repository skills are discovered under `.agents/skills`;
- `SKILL.md` is required;
- skill name and description support progressive disclosure;
- scripts, references, assets, and metadata are optional;
- instruction-only is the default;
- skills should be focused on one job.

## Codex — Best Practices

Official documentation:

https://developers.openai.com/codex/learn/best-practices

Key documented points:

A useful `AGENTS.md` can cover:

- repository layout;
- run/build/test/lint commands;
- engineering conventions;
- constraints;
- definition of done / verification.

## OpenAI Agents SDK — Overview

Official documentation:

https://developers.openai.com/api/docs/guides/agents

Key documented concepts include:

- agent definitions;
- tools;
- runtime/state;
- orchestration;
- guardrails;
- results/state;
- integrations;
- observability;
- evaluation.

## OpenAI Agents SDK — Running Agents / Conversation State

Official documentation:

https://developers.openai.com/api/docs/guides/agents/running-agents

The SDK supports multi-turn state through sessions and other continuation strategies.

## OpenAI Agents SDK — Function Tools

Official documentation:

https://openai.github.io/openai-agents-python/tools/

Function tools can derive schemas from typed function arguments and support validation constraints.

## OpenAI Agents SDK — Context

Official documentation:

https://openai.github.io/openai-agents-python/context/

Runtime context can carry application-owned state and dependencies through agent/tool execution.

## OpenAI Agents SDK — Guardrails

Official documentation:

https://openai.github.io/openai-agents-python/guardrails/

Guardrails are executable checks for:

- user input;
- agent output;
- tool inputs/outputs.

This supports keeping response style control separate from safety/validation guardrails.

## OpenAI Agents SDK — Structured Output

Official documentation:

https://openai.github.io/openai-agents-python/ref/agent_output/

The SDK supports schema-backed agent output and validation.

## OpenAI Agents SDK — Tracing / Observability

Official documentation:

https://developers.openai.com/api/docs/guides/agents/integrations-observability

Tracing can record:

- model calls;
- tool calls;
- handoffs;
- guardrails;
- custom spans.

## OpenAI Agents SDK — MCP

Official documentation:

https://openai.github.io/openai-agents-python/mcp/

MCP standardizes how applications expose tools and context to language models and is optional for an application that can use ordinary function tools directly.

---

# 56. Final Instruction to the Coding Agent

Do not blindly recreate the example architecture.

Your job is to:

```text
UNDERSTAND EXISTING SYSTEM
        ↓
MAP RESPONSIBILITIES
        ↓
IDENTIFY REAL GAPS
        ↓
DESIGN MINIMUM NECESSARY CHANGES
        ↓
RESTRUCTURE SAFELY
        ↓
TEST
        ↓
EVALUATE AGENT BEHAVIOR
        ↓
REMOVE OBSOLETE CODE
```

The objective is not to maximize the number of files.

The objective is to create a system where:

- development instructions are clear;
- runtime instructions are clear;
- task workflows are reusable;
- tools are controlled;
- business logic is deterministic where possible;
- data is validated;
- conversation context works;
- responses are consistent and adaptive;
- security does not depend only on prompt text;
- the architecture remains understandable and testable.
