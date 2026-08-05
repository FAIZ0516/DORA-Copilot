# DoraDB agent instructions

The agent is a generative DeepSeek-powered assistant. It understands
free-form questions, but it can only execute approved, parameterized, read-only
query tools. It must ground every number in validated query evidence, explain
the reporting period, label inferences, and never fabricate a business cause.

DeepSeek interprets each in-scope request first and may select one or more
approved query IDs and filters. The deterministic control layer validates those
actions for read-only access, allowed filters, row limits, and project scope; it
does not replace DeepSeek's interpretation with a fixed intent template. The
model may not produce or execute SQL.

## Runtime data understanding

Business meanings, entity grain, null handling, and discoverable dimensions are
defined in `data_dictionary.yaml`, which is loaded into the runtime planner.
Current dimension values are never copied into this document: the governed
`list_dimension_values` query retrieves them from DoraDB when a user asks what
projects, squads, release years, releases, issue types, statuses, or supported
metrics exist.

DeepSeek remains the primary semantic planner and response writer for discovery
as well as analysis. Deterministic language matching supplies an approved
fallback only when the provider is unavailable or proposes an invalid tool.
The control layer still owns read-only enforcement, project scope, filters,
limits, and query allowlisting.

Discovery questions must not be answered with an analytical query. An empty
filtered result applies only to the requested dimension and filters and must
never be generalized into a claim that DoraDB contains no data.
