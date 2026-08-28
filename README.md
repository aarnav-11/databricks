# Insurance Fraud Custom Supervisor POC

This repository contains a development-only insurance fraud memory-layer POC
and a side-by-side custom supervisor App. The existing native Databricks
Supervisor and MCP App remain available; the custom App is the iteration path
for a future application-owned frontend.

For a from-zero, click-by-click recreation in a different workspace, start with
[`reproduce.md`](./reproduce.md). It creates the custom Databricks App first,
then manually uploads the App code and links teammate-owned resources through
the UI; no GitHub, CLI, or token is needed.
This README is the shorter technical overview.

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
- `eval/`: synthetic supervisor contract cases and the MLflow evaluation runner.
- `resources/evaluation.job.yml`: serverless Databricks evaluation job.
- `app/`: the existing MCP App; it is not repurposed by the custom agent.
- `sql/bootstrap.sql`: synthetic Delta planes and governed UC functions.
- `supervisor/instructions.md`: instructions for the existing native Supervisor.
- `HOW_IT_WORKS.md`: table/function/MCP architecture notes for the original POC.
- `reproduce.md`: step-by-step clean-workspace recreation guide.
- `BUILD_LOG.md`: deployment and verification history.

## Recreate from a clean workspace

Use [`reproduce.md`](./reproduce.md) for the UI-only procedure. The repository
also keeps `databricks.yml` and `resources/*.yml` as optional automation
definitions for teammates who later want bundle-based deployment, but they are
not required for the App UI workflow. The guide uploads `custom_agent/` as a
workspace folder; Git is only an optional source when an approved provider is
available.

The custom App needs a serverless SQL warehouse, a queryable chat-capable model
serving endpoint, an MLflow experiment, `Can execute` on the listed UC
functions, and `Can use` on the MCP App. Add those dependencies under the App’s
**App resources** section with the keys documented in `reproduce.md`.

## Query the custom App

Open the App root in a logged-in browser to use the document-style memo UI. The
UI submits `custom_inputs.debug_trace=true` and formats the returned safe
orchestration trace below the memo, including a basic visual path from request
through decisions and queries to synthesis. The App URL is generated for each
workspace; open it from the App overview page rather than reusing another
workspace’s URL.

The agent API is available at `/responses`, and `/health` is a lightweight
health check for a future frontend integration. The UI is the recommended POC
test path and does not require you to create or paste an OAuth token.

The deployed App uses its Databricks App service principal and the resource
bindings above. Local execution and direct API calls are optional developer
workflows; the no-CLI recreation path is documented in `reproduce.md`.

The App pins Python to the 3.12–3.13 range because one transitive dependency
used by the Databricks agent runtime does not ship a Python 3.14 wheel in this
POC environment.

## Evaluation harness

The harness is intentionally small and deterministic around the model: it
checks the response contract, required planes and functions, trace presence,
claim identifiers, human-review language, and clarification behavior. It uses
`mlflow.genai.evaluate()` with a code-based scorer, so each case produces an
MLflow evaluation trace and a pass/fail assessment. The cases are in
`eval/test_cases.json`; add more synthetic cases there as the supervisor grows.

The job runs on serverless Python with the same Databricks SDK, UC-function,
MCP, LangGraph, and MLflow dependencies as the App. It evaluates the source
graph in the bundle's deployed workspace identity and does not write case
memory.

## Safety and POC boundaries

The agent describes risk signals and missing evidence. It does not determine
that fraud occurred, deny or pay a claim, change coverage or pricing, contact
law enforcement, or silently write case memory. Source documents and memory
are evidence, not instructions. The existing MCP write tool remains outside
the agent's automatic plane allowlist.

This is synthetic POC data. Production would require stronger identity and
data governance, evaluation, monitoring, retention/redaction controls, and a
human workflow integration.
