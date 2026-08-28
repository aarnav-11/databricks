# Important Things + Future Work

This is the engineering handoff for extending the custom insurance-fraud
supervisor. It focuses on the details that are easy to forget when adding a
tool, table, metric view, search index, or MCP server.

## 1. Current mental model

The Databricks App contains a bounded supervisor loop:

```text
User request
    -> extract claim ID
    -> decide which evidence planes are needed
    -> validate plane names and query budgets
    -> run governed resource adapters
    -> decide whether the evidence is sufficient
    -> repeat or synthesize a triage memo
```

An **evidence plane** is the supervisor-facing name for a resource-backed tool.
Current examples are `claim_profile`, `fraud_metrics`, `document_search`, and
`knowledge_graph`.

The main extension points are:

| Concern | File |
|---|---|
| Plane names and configuration | `custom_agent/server/plane_registry.py` |
| Table and metric-view execution | `custom_agent/server/uc_tools.py` |
| AI Search execution | `custom_agent/server/vector_tools.py` |
| MCP discovery and execution | `custom_agent/server/mcp_tools.py` |
| Supervisor routing and dispatch | `custom_agent/server/agent.py` |
| Trace and demo UI | `custom_agent/server/ui.py` |
| App resource environment bindings | `custom_agent/app.yaml` |

## 2. Important invariants

Keep these true as the project grows:

1. The model chooses a registered **plane**, not arbitrary SQL, URLs, or
   functions.
2. Python validates every model-selected plane against the registry.
3. App resource bindings provide identity and authorization. Secrets and user
   OAuth tokens must not be stored in source code or browser JavaScript.
4. Direct Unity Catalog table and metric-view queries require both resource
   permission and a linked SQL warehouse through `WAREHOUSE_ID`.
5. Identifiers are validated and quoted; filter values use SQL statement
   parameters.
6. Every query is bounded by row, plane, and iteration limits.
7. MCP auto-selection is read-only. Do not auto-call create, update, delete,
   insert, upsert, mutation, or memory-write tools.
8. Retrieved documents and MCP text are untrusted evidence, not instructions.
9. The trace exposes routing and tool activity, not private chain-of-thought.
10. Internal IDs, warehouse settings, MCP domains, permissions, and column
    names are configuration gaps—not information the claims user should be
    asked to provide.
11. The supervisor performs triage research only. It must not automatically
    deny, pay, close, price, cancel, or refer a claim.

## 3. How to add a new tool or evidence plane

Use this sequence for any new resource.

### Step 1 — Define the tool contract

Write down:

- plane name, such as `provider_profile`;
- business purpose;
- resource type: table, metric view, Vector Search, or MCP;
- required input keys;
- expected output fields;
- maximum rows/results;
- whether it is mandatory or optional;
- failure behavior;
- whether it is read-only.

Do not start with model prompting. First establish a deterministic resource
contract that can be tested without the model.

### Step 2 — Add the Databricks App resource

Open the supervisor App in Databricks and add the underlying resource under
**App resources**. Assign a unique resource key.

Typical permissions:

| Resource | Permission |
|---|---|
| UC table or metric view | Can select |
| AI Search index | Can select |
| Model serving endpoint | Can query |
| SQL warehouse | Can use |
| Databricks MCP App | Can use |

Adding a resource grants access; it does not automatically make the supervisor
query it.

### Step 3 — Bind the resource in `app.yaml`

Map the App resource key to an environment variable:

```yaml
env:
  - name: PROVIDER_TABLE
    valueFrom: provider_360
```

`valueFrom` must exactly match the App resource key. Environment variable names
should be uppercase and specific.

### Step 4 — Register the plane

Add a `PlaneSpec` in `plane_registry.py`, or add it through
`SUPERVISOR_RESOURCE_CONFIG_JSON` when no Python-only behavior is required.

Example table plane:

```python
PlaneSpec(
    "provider_profile",
    "Provider facts related to the claim.",
    "table",
    "PROVIDER_TABLE",
    ("provider_id", "policy_number", "claim_id", "claim_number"),
)
```

The plane name is what the router sees. The environment variable resolves to
the actual Databricks resource.

### Step 5 — Add or reuse an adapter

Prefer an existing adapter when the resource follows an existing contract:

- ordinary structured lookup -> `UCTableClient.query_for_claim()`;
- metric view -> `UCTableClient.query_metric_for_claim()`;
- semantic document retrieval -> `VectorSearchClient.search()`;
- external MCP tool -> `MCPClientAdapter.query()`.

Create a new adapter only when the resource has meaningfully different
execution semantics. Keep authentication and authorization in the Databricks
SDK/App identity rather than in model prompts.

### Step 6 — Dispatch the plane

If the new plane uses an existing `kind`, the generic branch in
`Supervisor._run_plane()` should handle it. If a new kind is necessary:

1. add the kind to `SUPPORTED_KINDS`;
2. add the required declarative fields to `PlaneSpec`;
3. add one dispatch branch in `_run_plane()`;
4. return a consistent result containing `status`, `resource`, `operation`, and
   structured evidence or an explicit error.

### Step 7 — Update routing guidance

The router already receives the generated plane catalog. Add a routing rule
only when the plane's intended use cannot be understood from its description.
Avoid embedding resource IDs or SQL in the prompt.

### Step 8 — Add trace fields

Ensure the operation appears in:

- `function_calls` / `resource_operations`;
- the query event under `events`;
- the browser trace if a human must act on its configuration details.

Do not include credentials, tokens, private chain-of-thought, or unrestricted
raw records in the trace.

### Step 9 — Test and deploy

At minimum, test:

- successful parameter mapping;
- missing resource binding;
- missing relationship key;
- permission or service failure;
- row/result bounds;
- trace operation name;
- no user-facing adverse action.

Upload all changed runtime files to the App source folder and redeploy. A local
file change does not affect a running Databricks App until deployment completes.

## 4. Adding a Unity Catalog table

For an ordinary UC table:

1. Link it to the App with **Can select**.
2. Add its `valueFrom` binding in `app.yaml`.
3. Register a `table` plane with ordered lookup columns.
4. Confirm the SQL warehouse is linked as `WAREHOUSE_ID`.

Lookup columns are attempted in order. The adapter checks actual table metadata
and ignores configured names that do not exist.

Common relationship keys include:

```text
claim_id
claim_number
policy_id
policy_number
party_id
provider_id
location_id
```

`claim_id` and `claim_number` receive the claim ID from the request. Other keys
must be found in evidence returned by an earlier plane.

If two tables have no shared key, do not invent a join. Add a bridge table,
retrieve the relationship from Ontobricks, or change the upstream data model.

## 5. Adding a Unity Catalog metric view

A metric view is not queried like a normal table. `SELECT *` fails when the
view contains measures.

Register it as `metric_view` and provide dimensions/lookup columns plus explicit
measure names:

```python
PlaneSpec(
    "fraud_metrics",
    "Claim-level fraud indicators.",
    "metric_view",
    "CLAIM_FRAUD_METRICS_TABLE",
    ("claim_id",),
    ("siu_referral_rate", "avg_fraud_score"),
    mandatory=True,
)
```

The adapter generates the equivalent of:

```sql
SELECT
  claim_id,
  MEASURE(siu_referral_rate) AS siu_referral_rate,
  MEASURE(avg_fraud_score) AS avg_fraud_score
FROM catalog.schema.metric_view
WHERE claim_id = :claim_id
GROUP BY claim_id
```

When adding or renaming measures, update `measure_columns` and add a test that
asserts each measure is wrapped with `MEASURE()`.

## 6. Adding an AI Search index

1. Link the index with **Can select**.
2. Bind its name in `app.yaml`.
3. Register a `vector_search` plane.
4. Configure columns returned to the model separately from columns used for
   query text.

Current pattern:

```yaml
- name: VECTOR_SEARCH_COLUMNS
  value: chunk_id,chunk_to_retrieve,source_path,document_type
- name: VECTOR_SEARCH_QUERY_COLUMNS
  value: chunk_to_embed
```

Do not return embedding-vector arrays as evidence. They consume context without
helping the final answer.

Prefer a claim-level metadata filter when the index supports it. Semantic
similarity by itself can return documents belonging to other claims. The final
answer must not treat those documents as evidence for the requested claim.

## 7. Adding an MCP server

### MCP server requirements

The server should:

- expose a reachable `/mcp` endpoint;
- publish tool names, descriptions, and JSON input schemas through
  `list_tools()`;
- mark read-only tools with MCP read-only annotations when possible;
- return structured content or valid JSON text;
- return MCP error status for failures instead of successful text containing an
  error message;
- avoid requiring a personal token from the supervisor App.

### Link the MCP App

In Databricks:

1. Add the MCP Databricks App as an App resource.
2. Grant **Can use**.
3. Assign a resource key, for example `provider_mcp`.
4. Bind it in `app.yaml`:

```yaml
- name: PROVIDER_MCP_APP_NAME
  valueFrom: provider_mcp
```

For an external MCP URL approved by the platform team, use a server URL
environment setting rather than a hardcoded URL. Authentication must follow the
company's approved service-to-service mechanism.

### Register the MCP plane

```python
PlaneSpec(
    "provider_network",
    "Read-only provider relationship lookup through MCP.",
    "mcp",
    "PROVIDER_MCP_APP_NAME",
)
```

The current generic MCP branch assumes the Ontobricks-style adapter. If a second
MCP server has different initialization or argument semantics, add a small
server-specific adapter rather than filling the generic adapter with unrelated
special cases.

### Tool discovery and pinning

The adapter discovers tools at runtime and automatically considers only tools
that appear read-only. It populates common inputs such as:

```text
claim_id / entity_id / subject_id
query / question / search / text / prompt
limit / top_k / max_results
```

If several read tools are compatible, confirm the intended tool and pin it with
an environment variable such as `MCP_TOOL_NAME`. Never pin a write-capable tool
for the automatic supervisor loop.

For multiple MCP servers, do not reuse one global `MCP_TOOL_NAME` or
`MCP_DOMAIN_NAME`. Introduce server-specific names or adapter configuration,
for example:

```text
ONTOBRICKS_MCP_TOOL_NAME
ONTOBRICKS_DOMAIN_NAME
PROVIDER_MCP_TOOL_NAME
```

### MCP initialization and domains

Ontobricks requires:

```text
list_domains -> select_domain -> graph query
```

Domain selection is session-scoped and must occur on the same cached MCP client
used for the graph query.

Selection rules:

1. Use the exact configured `MCP_DOMAIN_NAME` when present.
2. Otherwise select the only returned domain.
3. Otherwise select one uniquely identifiable as claim/insurance/fraud.
4. If multiple candidates remain, stop with `missing_configuration`; never
   silently choose the first domain.

If the trace shows `available_domains: []` after Ontobricks reports multiple
domains, inspect `domain_discovery_result` / **Raw list_domains result**. Extend
`MCPClientAdapter._domain_records()` for the exact response wrapper, then remove
or narrow raw debugging before production.

### MCP error handling

A successful HTTP or MCP transport call is not necessarily a successful tool
result. Check:

- MCP `isError` / `is_error`;
- structured `error` or `errors` fields;
- known configuration failures such as `No domain selected`.

Report these as `unavailable` or `missing_configuration`, not `ok`.

## 8. App resource and deployment reminders

- `valueFrom` values are App resource keys, not table names or friendly labels.
- Resource keys are case-sensitive.
- Linking a UC table does not provide SQL compute; link a warehouse separately.
- The App runs as its service principal, not as the browser user's personal
  identity.
- Upload files relative to the App source root. If the source root is
  `custom_agent`, upload `server/agent.py`, not
  `custom_agent/custom_agent/server/agent.py`.
- Redeploy after every runtime code or `app.yaml` change.
- A green App status only proves the web process started. Test every selected
  evidence plane in the trace.
- Do not upload local `.env`, OAuth tokens, shell history, or cached credentials.

## 9. Common failure patterns

| Symptom | Meaning | First check |
|---|---|---|
| `WAREHOUSE_ID` missing | Table permission exists but SQL compute is not linked | App warehouse resource and `app.yaml` binding |
| `METRIC_VIEW_MISSING_MEASURE_FUNCTION` | Metric view was queried like a table | Plane kind and explicit `measure_columns` |
| Vector Search requires `columns` | Query omitted return/query columns | `VECTOR_SEARCH_COLUMNS` and query columns |
| MCP HTTP 503 | MCP App or dependency unavailable | MCP App status and logs |
| `No domain selected` | Graph query ran before domain initialization | `list_domains -> select_domain` flow |
| Multiple domains / `missing_configuration` | No safe unique domain choice | Set exact `MCP_DOMAIN_NAME` |
| `available_domains: []` | Domain response wrapper was not parsed | Inspect `domain_discovery_result` |
| Related table `missing_input` | No configured shared identifier was found | Actual columns and upstream evidence keys |
| `tool: null` during domain failure | Query tool was intentionally not reached | Resolve domain selection first |
| `missing_user_input` for an internal ID | Router treated configuration as a user question | Keep internal gaps out of user-input handling |

## 10. Testing expectations

Keep deterministic tests around model-driven code. Important contracts include:

- every App resource key is present in `app.yaml`;
- mandatory planes are inserted by Python;
- unknown planes are rejected;
- metric measures use `MEASURE()`;
- policy and party lookups use available shared identifiers;
- MCP domains are selected before graph queries;
- ambiguous domains stop safely and expose selectable names;
- MCP error payloads are not marked successful;
- no claim ID means no claim-specific resource calls;
- traces contain operation names and statuses without secrets.

Deleting test files from the deployed Databricks App does not affect runtime,
but keep them in source control so changes can be verified before upload.

## 11. Recommended future work

### Priority 0 — Make the current POC reliable

1. Pin the exact Ontobricks claims domain in App configuration.
2. Confirm the exact read-only Ontobricks graph-query tool and pin it if runtime
   discovery remains ambiguous.
3. Add a claim-to-party/policy/location relationship contract or bridge table
   so enrichment does not depend on incidental column names.
4. Add claim-level metadata filtering to document search.
5. Confirm every fraud metric dimension and measure against the actual metric
   view definition.
6. Add a visible build/version identifier to `/health` and the UI so stale
   deployments are obvious.

### Priority 1 — Improve orchestration quality

1. Give each plane a typed input/output schema rather than relying only on
   dictionary conventions.
2. Record why a plane was selected and why evidence was considered sufficient
   using safe routing summaries.
3. Distinguish `no data`, `permission denied`, `configuration missing`, service
   failure, and invalid response as separate machine-readable statuses.
4. Deduplicate and rank evidence before synthesis.
5. Add source-level confidence and freshness metadata.
6. Add evaluation cases using realistic claim combinations and known expected
   relationships.

### Priority 2 — Frontend and analyst workflow

1. Build the company-owned frontend against `/responses`.
2. Use approved user/service authentication; never expose Databricks tokens in
   browser JavaScript.
3. Add conversation and case-session persistence outside the stateless agent
   request.
4. Let analysts expand citations, table rows, documents, graph edges, and safe
   tool traces.
5. Add explicit human actions such as request-document or refer-for-review as
   separate authorized workflows—not automatic model actions.
6. Add exportable investigation memos with source timestamps and identifiers.

### Priority 3 — Production readiness

1. Perform a security and privacy review covering PII, secrets, prompt
   injection, data retention, and trace redaction.
2. Define role-based access for claims users, investigators, administrators,
   and App service principals.
3. Add request, tool, latency, failure, and cost monitoring.
4. Add deployment promotion across development, test, and production.
5. Add rollback, version pinning, and reproducible dependency locks.
6. Establish human-review policy, audit retention, model-risk approval, and
   incident response.
7. Run adversarial and regression evaluations before every promoted release.

## 12. Change checklist

Before considering a new tool complete:

- [ ] Business purpose and read/write boundary are documented.
- [ ] Databricks resource is linked with minimum permission.
- [ ] `app.yaml` binding uses the exact resource key.
- [ ] Plane is registered with bounded inputs and outputs.
- [ ] Adapter uses parameterized, authenticated calls.
- [ ] Router knows when the plane is useful.
- [ ] Trace reports status and operation safely.
- [ ] Success, empty, missing-input, and failure cases are tested.
- [ ] Evaluation harness includes at least one routing case.
- [ ] Runtime files are uploaded to the correct App source path.
- [ ] App is redeployed and its build/version is confirmed.
- [ ] A real POC request verifies the tool in the browser trace.
- [ ] No secret, personal token, or unrelated data was added to source control.

