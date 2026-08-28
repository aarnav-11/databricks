# Insurance Fraud Custom Supervisor POC

This repository contains a Databricks App that runs a bounded supervisor loop
for claim-triage research. The current implementation uses the exact App
resources listed below and exposes both a browser UI and a Responses-compatible
`/responses` endpoint.

For a click-by-click build in a different Azure Databricks workspace, use
[`reproduce.md`](./reproduce.md).

## Current App resources

These keys are case-sensitive and must match `custom_agent/app.yaml`.

| Resource type | Databricks resource | App resource key | Code environment variable |
|---|---|---|---|
| SQL warehouse | Workspace-selected serverless warehouse | `sql-warehouse` | `WAREHOUSE_ID` |
| Databricks App | `mcp-ontobricks-07x` | `ontobricks_kg` | `MCP_APP_NAME` |
| UC table | `dmpipeline-dev.ri_gold.claim_360` | `claim_360` | `CLAIM_TABLE` |
| UC table | `dmpipeline-dev.ri_gold.party_360` | `party_360` | `PARTY_TABLE` |
| UC table | `dmpipeline-dev.ri_gold.location_360` | `location_360` | `LOCATION_TABLE` |
| UC table | `dmpipeline-dev.ri_gold.policy_360` | `policy_360` | `POLICY_TABLE` |
| Serving endpoint | `databricks-claude-opus-5` | `LLM` | `MODEL_ENDPOINT` |
| AI Search index | `dmpipeline-dev.plane4.chunks_demo_index` | `vector-search-index` | `VECTOR_SEARCH_INDEX` |
| UC table | `dmpipeline-dev.ri_gold.claim_fraud_metrics` | `claim_fraud_metrics` | `CLAIM_FRAUD_METRICS_TABLE` |

The permissions shown in the current App configuration are `Can use` for the
MCP App, `Can query` for the serving endpoint, and `Can select` for each UC
table and the AI Search index.

## Important: direct table queries need a SQL warehouse

The table resources authorize the App service principal to select data, while
the SQL warehouse provides compute. `custom_agent/app.yaml` now contains this
required binding:

```yaml
  - name: WAREHOUSE_ID
    valueFrom: sql-warehouse
```

Before deploying, link one serverless SQL warehouse to the App with the exact
resource key `sql-warehouse` and **Can use**. If it is absent, deployment fails
resource resolution; older deployments without the binding start but report
`missing_resource: WAREHOUSE_ID` for every table plane.

## How the supervisor loop works

1. Extract a claim ID from the request.
2. Ask the model whether the accumulated evidence is enough.
3. Validate requested plane names against a declarative registry.
4. Always collect the baseline `claim_profile` and `fraud_metrics` planes.
5. Query up to three new planes in an iteration.
6. Feed results back into the router and repeat, with a four-iteration bound.
7. Produce a qualified triage memo and a safe orchestration trace.

The trace contains routing choices, resource operations, statuses, row counts,
and stopping reasons. It deliberately does not expose private model
chain-of-thought.

## Evidence planes

| Plane | Resource | Behavior |
|---|---|---|
| `claim_profile` | `claim_360` | Looks up the configured claim ID; mandatory baseline |
| `fraud_metrics` | `claim_fraud_metrics` | Retrieves claim-level fraud metrics; mandatory baseline |
| `party_profile` | `party_360` | Uses related party IDs found in earlier evidence, or `claim_id` if the table contains it |
| `location_profile` | `location_360` | Uses related location/address IDs found in earlier evidence |
| `policy_profile` | `policy_360` | Uses a related policy ID found in earlier evidence |
| `document_search` | `chunks_demo_index` | Runs a semantic query using the claim ID and user question |
| `knowledge_graph` | `mcp-ontobricks-07x` | Discovers MCP tools at runtime and invokes a compatible read-only tool |

Table identifiers and filter values are never pasted into arbitrary generated
SQL. Table names come only from App resource bindings, identifiers are
validated and quoted, values use SQL statement parameters, and each result is
bounded.

The current AI Search index is configured to return `chunk_id`,
`chunk_to_retrieve`, `source_path`, and `document_type`, while searching the
`chunk_to_embed` text column. `db_chunk_to_embed_vector` is intentionally not
returned because the embedding array is not useful answer evidence and would
inflate the model context. Change `VECTOR_SEARCH_COLUMNS` and
`VECTOR_SEARCH_QUERY_COLUMNS` when another index uses a different schema.

The MCP adapter calls `list_tools()` at runtime. If `MCP_TOOL_NAME` is set, it
uses that exact tool. Otherwise it considers only tools whose MCP annotations
or names indicate a read operation, rejects write-like names, and invokes a
tool only when its required inputs can be populated from the question and
claim ID. If no compatible tool exists, the trace lists the discovered names
and asks for `MCP_TOOL_NAME`; it does not guess a write-capable tool.

## Add another resource without another hardcoded branch

The defaults live in `custom_agent/server/plane_registry.py`. To add or
override a plane from configuration:

1. Link the new resource in the App UI and give it a unique resource key.
2. Map the key to an environment variable in `custom_agent/app.yaml`.
3. Add a JSON plane object through `SUPERVISOR_RESOURCE_CONFIG_JSON`.

Example for a future provider table:

```yaml
  - name: PROVIDER_TABLE
    valueFrom: provider_360
  - name: SUPERVISOR_RESOURCE_CONFIG_JSON
    value: '{"planes":[{"name":"provider_profile","description":"Related provider details.","kind":"table","env_var":"PROVIDER_TABLE","lookup_columns":["provider_id","claim_id"]}]}'
```

Supported `kind` values are `table`, `vector_search`, and `mcp`. An entry with
the same `name` replaces the default, which is useful when another workspace
uses different relationship columns.

If claim IDs do not look like `CLM-1001`, add `CLAIM_ID_REGEX` and optionally
`CLAIM_ID_EXAMPLE` as plain environment values in `app.yaml`.

## Repository layout

- `custom_agent/`: deployable supervisor Databricks App.
- `custom_agent/server/plane_registry.py`: dynamic evidence-plane registry.
- `custom_agent/server/uc_tools.py`: safe table-query adapter.
- `custom_agent/server/vector_tools.py`: AI Search adapter.
- `custom_agent/server/mcp_tools.py`: MCP discovery and read-only call adapter.
- `custom_agent/server/agent.py`: bounded LangGraph loop and Responses handlers.
- `custom_agent/server/ui.py`: document-style demo UI and trace diagram.
- `custom_agent/tests/`: local registry contract tests.
- `reproduce.md`: Azure Databricks UI recreation instructions.
- `app/`, `sql/`, `supervisor/`, and `resources/`: earlier synthetic POC and
  optional automation artifacts; they are not uploaded with the current
  supervisor App.

## Test the App

Open the App URL from **Databricks Apps → your App → Open app**. A sample is:

```text
For CLM-1001, give me a concise fraud-risk triage summary and explain which resources were consulted.
```

The UI sends `custom_inputs.debug_trace=true`, renders the answer as a memo,
and visualizes each decision and resource operation. `/health` remains the
lightweight availability check for frontend integration.

Run the dependency-light registry tests locally with:

```text
PYTHONPATH=custom_agent python3 -m unittest discover -s custom_agent/tests -v
```

The MLflow harness in `eval/evaluate_supervisor.py` now checks the same plane
names and resource operations. Its Databricks Job definition remains in
`resources/evaluation.job.yml`; it needs a SQL warehouse and an MLflow
experiment because it verifies successful table operations and records runs.

## POC boundary

The supervisor summarizes risk signals and missing evidence. It does not decide
that fraud occurred, deny or pay a claim, change coverage or pricing, contact
law enforcement, or silently write case memory. Human review remains required.
