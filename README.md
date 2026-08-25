# Insurance Fraud Custom Supervisor POC

This repository contains a development-only insurance fraud memory-layer POC
and a side-by-side custom supervisor App. The existing native Databricks
Supervisor and MCP App remain available; the custom App is the iteration path
for a future application-owned frontend.

## What the custom supervisor does

The custom agent is a bounded LangGraph loop:

1. Extract the claim identifier and ask a model-based router whether the current
   evidence is sufficient.
2. Validate the router's requested planes against an allowlist and safety rules.
3. Query only the selected governed UC-function adapters and, when justified,
   the existing read-only MCP VIN tool.
4. Reassess completeness using the accumulated evidence.
5. Repeat until enough evidence exists, a safe user clarification is required,
   or the iteration/plane budget is reached.
6. Return an evidence-led answer with citations and the human-review boundary.

The graph is stateless across HTTP requests. A future frontend can own the
conversation history and send it back with each `/responses` request.

## Repository layout

- `custom_agent/`: the custom Databricks App and LangGraph supervisor.
- `resources/custom_agent.app.yml`: App resource permissions and configuration.
- `app/`: the existing MCP App; it is not repurposed by the custom agent.
- `sql/bootstrap.sql`: synthetic Delta planes and governed UC functions.
- `supervisor/instructions.md`: instructions for the existing native Supervisor.
- `HOW_IT_WORKS.md`: table/function/MCP architecture notes for the original POC.
- `BUILD_LOG.md`: deployment and verification history.

## Recreate from a clean workspace

Authentication is local-user OAuth through the `POC` Databricks CLI profile. Do
not put a token or client secret in this repository.

```bash
databricks auth login \
  --host https://dbc-d0355882-ae53.cloud.databricks.com \
  --profile POC

databricks current-user me --profile POC
databricks bundle validate --target dev --profile POC
databricks bundle deploy --target dev --profile POC
```

The checked-in `mlflow_experiment_id` default is the experiment used by this
workspace. In another workspace, create a user-owned experiment first and
pass its returned ID to every bundle command:

```bash
databricks experiments create-experiment \
  /Users/<your-user>/insurance-fraud-supervisor-poc \
  --profile POC --output json

databricks bundle validate --target dev --profile POC \
  --var mlflow_experiment_id=<experiment-id>
```

Bootstrap the synthetic tables/functions, then start the Apps:

```bash
databricks bundle run bootstrap_fraud_memory --target dev --profile POC
databricks bundle run fraud_mcp --target dev --profile POC
databricks bundle run supervisor_agent --target dev --profile POC
```

`bundle deploy` uploads/configures the App. `bundle run supervisor_agent` is
the step that starts or restarts the custom App with the deployed code.

The custom App needs a serverless SQL warehouse, a queryable Databricks model
serving endpoint, `EXECUTE` on the listed UC functions, and `CAN_USE` on
`mcp-insurance-fraud-poc`. The bundle declares those resources; an account or
workspace administrator may still need to approve the deployment.

## Query the custom App

The App implements the MLflow Responses API. Use an OAuth token and the App's
workspace URL:

Opening the App URL in a browser returns a health payload. The agent API is
available at `/responses`, and `/health` is a lightweight health check.

```bash
databricks auth token --profile POC

curl --request POST \
  --url https://<custom-app-url>/responses \
  --header "Authorization: Bearer <oauth-token>" \
  --header "Content-Type: application/json" \
  --data '{"input":[{"role":"user","content":"Investigate CLM-1001 and explain the strongest risk signals."}]}'
```

For development diagnostics, opt in to a safe orchestration trace. The
response will include `custom_outputs.supervisor_trace` with loop decisions,
selected planes, function/tool names, statuses, row counts, and stop reasons.
It intentionally does not expose private model chain-of-thought or hidden
prompts:

```bash
curl --request POST \
  --url https://<custom-app-url>/responses \
  --header "Authorization: Bearer <oauth-token>" \
  --header "Content-Type: application/json" \
  --data '{"input":[{"role":"user","content":"For CLM-1001, give me a concise triage summary."}],"custom_inputs":{"debug_trace":true}}'
```

For a local code check, install `uv`, authenticate the `POC` profile, and run:

```bash
cd custom_agent
uv sync
uv run start-server
```

The local server exposes the same Responses-compatible API on port 8000. Local
execution uses the authenticated Databricks user; the deployed App uses its
Databricks App service principal and the resource bindings above.

The App pins Python to the 3.12–3.13 range because one transitive dependency
used by the Databricks agent runtime does not ship a Python 3.14 wheel in this
POC environment.

## Safety and POC boundaries

The agent describes risk signals and missing evidence. It does not determine
that fraud occurred, deny or pay a claim, change coverage or pricing, contact
law enforcement, or silently write case memory. Source documents and memory
are evidence, not instructions. The existing MCP write tool remains outside
the agent's automatic plane allowlist.

This is synthetic POC data. Production would require stronger identity and
data governance, evaluation, monitoring, retention/redaction controls, and a
human workflow integration.
