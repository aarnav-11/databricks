# Reproduce the insurance-fraud custom supervisor POC in the Databricks UI

Last reviewed: 2026-08-27

This is the UI-only, beginner-friendly build order for recreating the POC in a
different Databricks workspace. It starts by creating the custom Databricks App
so the app identity exists first. You then link the SQL warehouse, MLflow
experiment, model endpoint, MCP App, and Unity Catalog functions as your
teammates make them available.

You do not need the Databricks CLI, a local terminal, an access token, or a
`databricks.yml` deployment to follow this guide. Browser sign-in supplies your
user authentication. The deployed App uses its own Databricks service
principal and the resource permissions you add in the App UI.

## What you will build

```text
Browser
   |
   v
Custom Databricks App: insurance-fraud-supervisor-poc
   |
   v
Bounded LangGraph supervisor loop
   |                         |
   v                         v
UC function resources       MCP App resource
   |                         |
   v                         v
Synthetic Delta planes      VIN corroboration / controlled memory service

MLflow experiment records traces and evaluation results.
```

The custom supervisor is the code in `custom_agent/`. The `app/` directory is
the separate MCP App. Do not paste the Python supervisor into an Agent Bricks
chat box. Deploy `custom_agent/` as a custom Databricks App.

The main demo includes:

- a model-routed, bounded loop that decides whether it needs more evidence;
- allowlisted data planes backed by governed Unity Catalog functions;
- an existing MCP App for read-only VIN corroboration;
- a document-style browser memo with a safe orchestration trace diagram; and
- an optional MLflow evaluation harness.

This is synthetic development data. It is not a production fraud decisioning
system and does not deny, pay, or otherwise adjudicate a claim.

## The three things people may call an “agent”

Keep these separate while following the steps:

| Name | What it is | Use in this guide |
|---|---|---|
| Custom supervisor App | Python/LangGraph code in `custom_agent/` hosted by Databricks Apps | **Yes — this is the primary build** |
| MCP App | A separate Databricks App exposing MCP tools from `app/` | Link it as a dependency when it exists |
| Native Agent Bricks Supervisor | A point-and-click supervisor created under the Agents area | Optional comparison only; not required |

If you want the code, loop, trace, and future-frontend API from this repository,
choose **Databricks Apps → Create a custom app**. Do not choose the native
Agent Bricks Supervisor wizard for the primary path.

## Build order at a glance

1. Create the custom App shell.
2. Connect the Git repository and identify `custom_agent/` as the App source.
3. Collect teammate resource names and IDs in the handoff table.
4. Create or verify the catalog, schema, tables, and UC functions.
5. Add each available dependency under the App’s **App resources** section.
6. Confirm the App’s `app.yaml` resource keys match the linked resources.
7. Deploy from Git in the Databricks UI.
8. Open the generated App URL and run the browser demo.
9. Optionally create the evaluation job through the Jobs UI.

You can complete steps 1–2 now even if the other team members are still
building their resources. Save the App without deploying it, then return to
step 5 whenever a dependency becomes available.

## Step 0 — Write down the values you will use

Open the repository in a browser or editor and keep this table beside the
Databricks tab. Replace a default only when your team has chosen a different
resource.

| Setting | Default for this POC | Where it is used |
|---|---|---|
| Custom App name | `insurance-fraud-supervisor-poc` | Databricks Apps; permanent name |
| Git repository | `https://github.com/aarnav-11/databricks` | App source |
| Git reference | `main` | Branch to deploy |
| App source path | `custom_agent` | The folder treated as the App root |
| Unity Catalog catalog | `workspace` | `FRAUD_CATALOG` |
| Unity Catalog schema | `insurance_fraud_poc` | `FRAUD_SCHEMA` |
| SQL warehouse | teammate-provided | `supervisor-warehouse` resource |
| MLflow experiment | teammate-provided or one you create | `supervisor-experiment` resource |
| Model serving endpoint | teammate-provided chat-capable endpoint | `supervisor-model` resource |
| MCP App | teammate-provided running App name | `supervisor-mcp-app` resource |

The App name can contain only lowercase letters, numbers, and hyphens. It must
be unique in the workspace and cannot be renamed later. Do not put a token,
password, or other secret in this table or in the repository.

## Step 1 — Create the custom Databricks App first

This creates the App identity and service principal before you link any
resources. Creating it does not deploy the code automatically.

### 1.1 Open Databricks Apps

1. Open the URL of the Databricks **workspace** where you want the POC.
2. Sign in with your normal browser login.
3. Look at the left sidebar.
4. If the sidebar is collapsed, click the **app switcher** in the upper-left.
5. Select **Databricks Apps**.

If **Databricks Apps** is not present, stop here and ask a workspace
administrator to enable Databricks Apps and serverless App compute. You cannot
fix a disabled workspace feature from the repository.

### 1.2 Create the App shell

1. On the Databricks Apps page, click **+ Create app**.
2. Select **Create a custom app**.
3. In **Name**, enter:

   ```text
   insurance-fraud-supervisor-poc
   ```

4. In **Description**, enter something like:

   ```text
   Development-only bounded supervisor for synthetic insurance-fraud triage.
   ```

5. Click **Next: Configure Git**.

### 1.3 Connect the repository

Use the repository that contains this project.

1. Select **GitHub** as the Git provider. If your team uses a fork, select the
   provider that hosts that fork.
2. Enter the repository URL:

   ```text
   https://github.com/aarnav-11/databricks
   ```

3. Select or enter the Git reference `main`.
4. If Databricks asks for Git credentials and the repository is private, click
   the option to configure a Git credential and complete the provider login.
   A public repository does not need a repository credential.
5. Click **Next: Configure**.

Do not enable automatic deployment yet unless your team specifically wants
every push to redeploy the POC. Manual deployment is easier while teammates
are still changing linked resources.

### 1.4 Save without deploying

1. Leave advanced settings at their defaults for now.
2. Do not try to add resources that do not exist yet.
3. Click **Create app**.
4. Wait for the App overview page to appear.
5. Confirm that the App exists and that you can see its overview, settings,
   resources, and deployment controls.

At this point the App shell is complete. It is normal for it not to be
`RUNNING` yet. Do not delete and recreate it when a teammate gives you a new
warehouse, model endpoint, or MCP App; add the new resource to this same App.

## Step 2 — Confirm which code Databricks will deploy

The repository has more than one deployable component. The supervisor App must
use the `custom_agent` directory as its top-level source directory.

### 2.1 Confirm the required files

The folder selected as the App source must contain these files:

```text
custom_agent/
├── app.yaml
├── pyproject.toml
├── requirements.txt
└── server/
    ├── agent.py
    ├── mcp_tools.py
    ├── plane_registry.py
    ├── start_server.py
    ├── uc_tools.py
    └── ui.py
```

`custom_agent/app.yaml` starts the server with `uv run start-server`.
Databricks reads this file from the root of the selected App source path.

Do not select the repository root for this App unless you intentionally copy
the custom agent files there. Do not select `app/`; that is the MCP App.

### 2.2 If the repository is private

On the App overview page, use **Configure Git credential** if Databricks shows
that control. You need permission to manage the App and a Git credential that
can read the repository. If you cannot configure it, ask the repository owner
or workspace administrator to grant access; do not paste a Git token into
`app.yaml`.

### 2.3 If you cannot use Git for this App

The primary path is Git because the source is already organized in this
repository. If your workspace requires workspace-folder deployments instead:

1. Open **Workspace** from the left sidebar.
2. Create or select a folder where you can store App files.
3. Use the workspace **Import** or **Upload** action to place the complete
   contents of `custom_agent/` into a dedicated folder.
4. Make sure `app.yaml`, `pyproject.toml`, `requirements.txt`, and the `server/`
   directory are at the folder’s top level.
5. Later, in the App overview page, click **Deploy** and select that folder.

Do not mix the Git and workspace-folder source methods for the same deployment.

## Step 3 — Collect the teammate handoff information

A resource must already exist before it can be added to an App. The user
adding it also needs **Can manage** permission on both the resource and the
App. Ask each teammate for the exact name or ID, not a screenshot or a
nickname.

Fill this table as the resources are created.

| Status | Teammate must provide | Databricks App resource type | Resource key to use | App permission |
|---|---|---|---|---|
| WAITING / READY | SQL warehouse ID or exact name | SQL warehouse | `supervisor-warehouse` | **Can use** |
| WAITING / READY | MLflow experiment ID or exact path | MLflow experiment | `supervisor-experiment` | **Can manage** |
| WAITING / READY | Serving endpoint name | Serving endpoint | `supervisor-model` | **Can query** |
| WAITING / READY | MCP App name | Databricks app | `supervisor-mcp-app` | **Can use** |
| WAITING / READY | UC functions listed in Step 5 | UC function | function-specific keys | **Can execute** |

Send teammates this minimum request:

> Please send the exact Databricks resource name/ID, confirm it is ready, and
> grant me enough permission to add it to the App. I need a SQL warehouse, an
> MLflow experiment, a chat-capable serving endpoint, the MCP App name, and the
> full three-level names of the UC functions.

### What “linking” means

The App has its own service principal. Adding a resource does two things:

1. it grants that service principal the selected permission on the existing
   resource; and
2. it exposes a stable environment value to the App using the resource key.

The resource is not copied, moved, or recreated. A teammate can continue to
own and update the resource after you link it.

### If a teammate is not finished

Leave that row as `WAITING`. Do not create a fake resource with a guessed name.
You can return to the same App later:

1. Open **Databricks Apps**.
2. Click `insurance-fraud-supervisor-poc`.
3. Open the App edit/configuration view.
4. Add the newly available resource under **App resources**.
5. Save and redeploy when the full required set is linked.

## Step 4 — Create or verify the Unity Catalog data plane

The App does not create its own tables or functions at runtime. The catalog,
schema, tables, and functions must exist first.

There are two valid paths. Use only one.

### Path A — Your teammates already own the data plane

Ask them for:

- catalog name;
- schema name;
- confirmation that the 11 POC tables exist; and
- the full three-level names of the 12 functions.

Use their catalog and schema in the handoff table. Skip the bootstrap script if
their data is the authoritative shared POC data.

### Path B — Bootstrap the synthetic POC data yourself in the UI

Use this path only if the team has not created the shared data plane.

#### 4.1 Choose or create a SQL warehouse

If a teammate already supplied a warehouse, use that one. Otherwise:

1. In the left sidebar, open **SQL** or **SQL Warehouses**.
2. Click **Create SQL warehouse**.
3. Give it a name such as `insurance-fraud-supervisor-poc`.
4. Choose **Serverless** if your workspace offers it.
5. Keep the smallest reasonable development size.
6. Click **Create**.
7. Record the warehouse ID from the warehouse details page.

This warehouse will be used both to run the bootstrap SQL and by the deployed
App. The App needs only **Can use** on it.

#### 4.2 Choose the catalog and schema

The checked-in synthetic SQL uses:

```text
catalog: workspace
schema: insurance_fraud_poc
```

If you use those exact names, no namespace edit is needed. If you choose a
different catalog or schema:

1. Make a copy of `sql/bootstrap.sql` in your editor.
2. Replace every occurrence of `workspace.insurance_fraud_poc` with
   `<your-catalog>.<your-schema>`.
3. Keep the periods between catalog, schema, and object names.
4. Later, update the `FRAUD_CATALOG` and `FRAUD_SCHEMA` values in
   `custom_agent/app.yaml` to the same names.

Do not replace only the first occurrence; the functions reference the tables
using fully qualified names throughout the file.

#### 4.3 Run the bootstrap SQL in SQL Editor

1. Open **SQL Editor** from the left sidebar.
2. Click **New query**.
3. At the top of the editor, select the warehouse from step 4.1.
4. Open `sql/bootstrap.sql` from the repository in your editor.
5. Copy the complete file and paste it into the SQL Editor.
6. If you selected a different catalog/schema, confirm the replacements from
   step 4.2 are present.
7. Confirm that **Run all statements** is selected.
8. Click **Run**.
9. Wait for all statements to finish.

The file ends with a sample score query. A successful run should return a row
for `CLM-1001`. The SQL Editor supports semicolon-separated multi-statement
queries; if your workspace shows a statement-level run option, keep **Run all
statements** selected for the bootstrap.

The script uses `INSERT OVERWRITE` for synthetic sample rows. Do not rerun it
against a teammate’s shared data unless you have agreed that resetting the POC
rows is safe.

#### 4.4 Verify tables and functions

In the same SQL Editor tab, run these checks one at a time:

```sql
SHOW TABLES IN workspace.insurance_fraud_poc;
```

```sql
SHOW USER FUNCTIONS IN workspace.insurance_fraud_poc;
```

```sql
SELECT *
FROM workspace.insurance_fraud_poc.score_claim('CLM-1001');
```

If you used another namespace, replace the namespace in each check. You should
see the POC tables, the listed UC functions, and a score row for `CLM-1001`.

## Step 5 — Link resources to the App in the Databricks UI

Do this from the App created in Step 1. You can add resources one at a time;
you do not need to wait for all teammates before linking the first one.

### 5.1 Open the App resources editor

1. Open **Databricks Apps**.
2. Click `insurance-fraud-supervisor-poc`.
3. Click **Edit** or open the App configuration/settings view.
4. Find **App resources**.
5. Click **+ Add resource**.

For every resource below, select the resource, choose the permission, set the
custom key exactly as shown, and save the resource. Resource keys are case
sensitive in the App configuration.

### 5.2 Add the SQL warehouse

1. Click **+ Add resource → SQL warehouse**.
2. Select the teammate’s warehouse, or the warehouse from step 4.1.
3. Select **Can use**.
4. Set **Custom key** to:

   ```text
   supervisor-warehouse
   ```

5. Click **Add** or **Save**.

The App receives the warehouse ID through `WAREHOUSE_ID`. Do not paste a
warehouse ID into the Python source.

### 5.3 Add the MLflow experiment

1. Click **+ Add resource → MLflow experiment**.
2. Select the experiment that the team will use for this App.
3. Select **Can manage** for this development POC. If the team only wants the
   App to record traces and not manage experiment settings, **Can edit** may be
   sufficient; confirm with the experiment owner.
4. Set **Custom key** to:

   ```text
   supervisor-experiment
   ```

5. Click **Add** or **Save**.

The App receives the experiment ID through `MLFLOW_EXPERIMENT_ID`.

If the experiment does not exist and you are responsible for creating it:

1. Open **Workspace**.
2. Navigate to a folder you own.
3. Use **Create → MLflow experiment**.
4. Name it `insurance-fraud-supervisor-poc`.
5. Create it and record its experiment ID.
6. Return to the App resource editor and link it as above.

### 5.4 Add the model serving endpoint

1. Click **+ Add resource → Serving endpoint**.
2. Select the teammate’s chat-capable endpoint.
3. Confirm that its state is **READY**.
4. Select **Can query**.
5. Set **Custom key** to:

   ```text
   supervisor-model
   ```

6. Click **Add** or **Save**.

The App receives the endpoint name through `MODEL_ENDPOINT`. Do not use **Can
manage** just to make inference work; **Can query** is the intended POC
permission.

If you are creating the endpoint yourself, open **Machine Learning → Serving**
and use the foundation-model or other chat-model flow available in your
workspace. The exact model catalog and endpoint creation controls vary by
workspace entitlement. The only value this App needs is a queryable,
Responses/ChatDatabricks-compatible endpoint that reaches **READY**.

### 5.5 Add the MCP App

The MCP App is a separate App. It must already exist and be `RUNNING` before
the supervisor can call it.

1. Click **+ Add resource → Databricks app**.
2. Select the teammate’s MCP App by its exact App name.
3. Select **Can use**.
4. Set **Custom key** to:

   ```text
   supervisor-mcp-app
   ```

5. Click **Add** or **Save**.

The App receives the MCP App name through `MCP_APP_NAME`. The supervisor uses
that name to resolve the MCP App URL and calls the MCP endpoint internally; you
do not paste the MCP URL into the supervisor code.

The MCP App itself has separate resources. In the MCP App’s own configuration,
its `app.yaml` uses the key `fraud-warehouse`, and its resource permissions
include the `case_memory` table with **Modify** when controlled memory writes
are enabled. Do not give the supervisor App Modify permission on
`case_memory`; the supervisor does not silently write case memory.

### 5.6 Add the Unity Catalog functions

The custom supervisor calls the functions through Databricks SQL. Add each
function as a separate resource.

For every function:

1. Click **+ Add resource → UC function**.
2. Select the function using its full three-level name.
3. Select **Can execute**.
4. Set the custom key shown in the table.
5. Click **Add** or **Save**.

Use these twelve functions and keys:

| Full function name | Custom key |
|---|---|
| `<catalog>.<schema>.get_claim_snapshot` | `claim-snapshot-function` |
| `<catalog>.<schema>.evaluate_claim_rules` | `claim-rules-function` |
| `<catalog>.<schema>.score_claim` | `claim-score-function` |
| `<catalog>.<schema>.get_claim_entities` | `claim-entities-function` |
| `<catalog>.<schema>.get_claim_network` | `claim-network-function` |
| `<catalog>.<schema>.search_claim_documents` | `claim-documents-function` |
| `<catalog>.<schema>.get_case_memory` | `case-memory-function` |
| `<catalog>.<schema>.get_business_terms` | `business-terms-function` |
| `<catalog>.<schema>.get_business_rules` | `business-rules-function` |
| `<catalog>.<schema>.get_model_metadata` | `model-metadata-function` |
| `<catalog>.<schema>.get_governance_controls` | `governance-function` |
| `<catalog>.<schema>.get_audit_events` | `audit-events-function` |

For the default POC namespace, replace `<catalog>.<schema>` with:

```text
workspace.insurance_fraud_poc
```

The custom keys for the functions are used to make the App configuration and
permissions easy to inspect. The Python agent still builds the full function
name from `FRAUD_CATALOG` and `FRAUD_SCHEMA`.

When adding a UC function, Databricks may automatically grant the App service
principal `USE CATALOG`, `USE SCHEMA`, and `EXECUTE`. If the automatic grant
cannot be applied, the catalog/schema/function owner or administrator must
grant those privileges before deployment.

### 5.7 Save and inspect the final resource list

Before leaving the resource editor, confirm that the App has:

- one SQL warehouse with `supervisor-warehouse` and **Can use**;
- one MLflow experiment with `supervisor-experiment`;
- one READY serving endpoint with `supervisor-model` and **Can query**;
- one RUNNING MCP App with `supervisor-mcp-app` and **Can use**; and
- all twelve UC functions with **Can execute**.

If one row is still `WAITING`, leave the App created but do not expect a
successful deployment until the missing dependency is linked.

## Step 6 — Confirm the App configuration file

The repository’s `custom_agent/app.yaml` is already written for UI resource
linking. Its important contents are:

```yaml
command: ["uv", "run", "start-server"]

env:
  - name: WAREHOUSE_ID
    valueFrom: supervisor-warehouse
  - name: MLFLOW_TRACKING_URI
    value: databricks
  - name: MLFLOW_REGISTRY_URI
    value: databricks-uc
  - name: MLFLOW_EXPERIMENT_ID
    valueFrom: supervisor-experiment
  - name: FRAUD_CATALOG
    value: workspace
  - name: FRAUD_SCHEMA
    value: insurance_fraud_poc
  - name: MODEL_ENDPOINT
    valueFrom: supervisor-model
  - name: MCP_APP_NAME
    valueFrom: supervisor-mcp-app
```

The `valueFrom` keys must match the custom resource keys from Step 5.
Databricks resolves them when it deploys the App:

| Environment variable | `valueFrom` key | Resolved value |
|---|---|---|
| `WAREHOUSE_ID` | `supervisor-warehouse` | SQL warehouse ID |
| `MLFLOW_EXPERIMENT_ID` | `supervisor-experiment` | MLflow experiment ID |
| `MODEL_ENDPOINT` | `supervisor-model` | Serving endpoint name |
| `MCP_APP_NAME` | `supervisor-mcp-app` | MCP App name |

If you use a catalog or schema other than `workspace.insurance_fraud_poc`,
edit only the two static values in `custom_agent/app.yaml`, commit the change to
the branch you will deploy, and make sure the SQL functions use the same
namespace.

Do not edit `app/app.yaml` for this step. That file belongs to the separate MCP
App. Do not edit `resources/custom_agent.app.yml` for the UI-only path; that
file is the optional Declarative Automation Bundle definition.

## Step 7 — Deploy the custom App from the Databricks UI

Do this only after the required resources are linked.

1. Open **Databricks Apps**.
2. Click `insurance-fraud-supervisor-poc`.
3. Click **Deploy**.
4. Choose **From Git**.
5. Select the configured Git repository.
6. For **Git reference**, enter `main` or the branch containing your latest
   `custom_agent/` code.
7. Set **Reference type** to **Branch**.
8. For **Source code path**, enter:

   ```text
   custom_agent
   ```

9. Click **Deploy**.
10. Wait for the deployment build and startup checks to finish.
11. Confirm the App status changes to **RUNNING**.

Databricks installs the dependencies from the App source and starts the
command in `custom_agent/app.yaml`. The App URL is generated from the App name
and workspace; it is different in every workspace. Do not reuse the URL from
the original demo workspace.

If the App configuration or resource bindings changed, redeploy the App from
the same Git branch so the new environment values are applied.

## Step 8 — Run the browser demo

No terminal or access token is needed for this test.

### 8.1 Open the App

1. On the App overview page, click the generated **App URL** or **Open app**.
2. If prompted, complete the normal Databricks browser sign-in.
3. Wait for the page titled **Insurance fraud supervisor**.

The page is the document-style UI in `custom_agent/server/ui.py`.

### 8.2 Run the basic claim test

1. Leave the default question, or paste:

   ```text
   For CLM-1001, give me a concise triage summary with the strongest risk signals and the next human-review step.
   ```

2. Click **Generate memo**.
3. Wait for the memo to appear.

A successful result should contain:

- a claim-specific triage memo for `CLM-1001`;
- evidence-led risk signals rather than a declaration that fraud occurred;
- a human-review next step; and
- an open **Supervisor orchestration trace** section.

The trace diagram shows the request, each decision, the selected planes, the
governed function/tool calls, and synthesis. It is intentionally a safe
execution trace. It does not reveal private model chain-of-thought, hidden
prompts, or secret values.

### 8.3 Run the clarification test

Replace the question with:

```text
What can you investigate?
```

Click **Generate memo**. The supervisor should ask for a claim identifier and
should not query claim-specific functions. This confirms that the loop can stop
when required information is missing.

### 8.4 Run the network-plane test

Replace the question with:

```text
For CLM-1002, show the linked entities and network signals, then recommend the smallest human review step.
```

The trace should include the `network` plane and the
`get_claim_network` function if that function is available and permitted.

### 8.5 Check the lightweight health route

Copy the App URL from the App overview page, append `/health`, and open it in
the same signed-in browser. A running server should return a small successful
health response. If the health route fails, use the App’s **Logs** tab before
debugging the data or model resources.

## Step 9 — Optional: create the evaluation harness through the Jobs UI

The App demo is complete without this step. The harness is for checking the
supervisor contract and recording evaluation traces in MLflow.

The existing evaluation code is `eval/evaluate_supervisor.py`, and its three
synthetic cases are in `eval/test_cases.json`.

### 9.1 Create a Lakeflow Job

1. Open **Jobs & Pipelines** from the left sidebar.
2. Click **Create → Job**.
3. Set the job name to:

   ```text
   insurance-fraud-supervisor-evaluation
   ```

4. Add a task with type **Python script**.
5. Set the task name to `evaluate_supervisor`.

### 9.2 Configure the Git source

1. In the Job details pane, click **Add Git settings**.
2. Enter the same repository URL used for the App.
3. Select the correct Git provider.
4. Select branch `main`, or the branch containing the supervisor code.
5. If prompted, configure Git credentials for the repository.
6. In the Python script task, set the script path to:

   ```text
   eval/evaluate_supervisor.py
   ```

The job checks out the repository so the script can import
`custom_agent/server/agent.py` and load `eval/test_cases.json`.

### 9.3 Configure serverless Python dependencies

1. In the Python script task, find **Environment and Libraries**.
2. Add a serverless Python environment. If the UI exposes an environment
   version, use version `2` or the current compatible version offered by your
   workspace.
3. Add these dependencies, one per entry:

   ```text
   mlflow[databricks]>=3.10.0
   databricks-sdk>=0.60.0
   databricks-agents>=1.9.3
   databricks-langchain>=0.17.0
   databricks-mcp
   langchain-core>=0.3.0
   langgraph>=1.1.0
   pydantic>=2.0.0
   python-dotenv>=1.0.0
   ```

4. Confirm or apply the environment.

If your workspace does not allow serverless Jobs, ask a Job administrator for
the approved development compute option. Do not add production compute for
this POC.

### 9.4 Add the Python script parameters

The Python script expects a JSON array of command-line-style arguments. In the
task’s **Parameters** field, enter the following and replace the angle-bracket
values with the resources actually linked in your workspace:

```json
[
  "--warehouse-id", "<warehouse-id>",
  "--catalog", "<catalog>",
  "--schema", "<schema>",
  "--model-endpoint", "<serving-endpoint-name>",
  "--mcp-app-name", "<mcp-app-name>",
  "--mlflow-experiment-id", "<experiment-id>"
]
```

For the default POC, the catalog and schema are `workspace` and
`insurance_fraud_poc`. The Job’s run-as identity needs permission to use the
warehouse, query the model endpoint, access the experiment, execute the UC
functions, and use the MCP App. App resource bindings do not automatically
grant those permissions to a separate Job identity.

### 9.5 Run and inspect the harness

1. Leave the schedule unset so the Job is manual.
2. Click **Save**.
3. Click **Run now**.
4. Open the run details and inspect the task output.
5. Confirm the JSON summary reports the case count and a
   `contract_pass_rate` of `1.0`.
6. Open the linked MLflow experiment and inspect the evaluation run and traces.

If a case fails, read the failed contract check in the Job output. The harness
checks trace presence, claim IDs, required planes/functions, human-review
language, and clarification behavior; it does not decide whether any claim is
fraudulent.

## Step 10 — Link future teammate changes without rebuilding the App

### 10.1 Teammate creates or changes an existing resource

1. Ask for the exact new resource name or ID.
2. Ask the owner to grant you permission to manage the resource and edit the
   App, if you do not already have it.
3. Open **Databricks Apps → insurance-fraud-supervisor-poc**.
4. Open the App configuration and **App resources**.
5. Add or replace the resource using the correct key from Step 5.
6. Save the App configuration.
7. Redeploy the App from the branch that contains the matching code/config.
8. Run the browser test again.

Changing the linked warehouse, experiment, model endpoint, or MCP App does not
require changing Python code because the App reads those values through
`valueFrom`.

### 10.2 Teammate creates a new UC function

Linking a new function gives the App permission to execute it, but it does not
automatically make the supervisor call it. For an existing plane, confirm the
function is one of the twelve names in Step 5. For a genuinely new plane, the
code change must include:

1. a new `PlaneSpec` in `custom_agent/server/plane_registry.py`;
2. the function mapping in `custom_agent/server/agent.py`;
3. a trace/evaluation case proving the new route; and
4. a new UC function resource link in the App UI.

Deploy the code and the resource link together, then rerun the browser test.

### 10.3 Teammate changes the MCP App

If the MCP App is replaced rather than updated:

1. remove or edit the old `supervisor-mcp-app` resource;
2. select the new running MCP App;
3. keep the custom key `supervisor-mcp-app`; and
4. redeploy the supervisor App.

If the trace reports an unavailable MCP tool or the request returns HTTP 503,
open the MCP App itself and check its status and logs first. Then confirm that
the supervisor’s App resource points to the new exact App name.

## Common problems and the UI fix

| Symptom | Check first | Fix |
|---|---|---|
| Databricks Apps is missing | Workspace feature availability | Ask an admin to enable Databricks Apps/serverless Apps |
| App exists but is not running | App overview status | Deploy the App after linking all required resources |
| Git deployment cannot read the repo | Git credential/provider | Configure the App service principal’s Git credential or use a permitted fork |
| `app.yaml` resource resolution fails | Resource key spelling | Match `supervisor-warehouse`, `supervisor-experiment`, `supervisor-model`, and `supervisor-mcp-app` exactly |
| `WAREHOUSE_ID` is missing | SQL warehouse resource | Add the warehouse with custom key `supervisor-warehouse` and **Can use** |
| Model call fails | Endpoint state and permission | Use a chat-capable endpoint in **READY** state with **Can query** |
| UC function is not visible | Function exists and you have **Can manage** | Ask the function owner/admin to grant access, then add it as **UC function → Can execute** |
| UC function returns permission denied | Catalog/schema/function privileges | Ask the owner/admin for `USE CATALOG`, `USE SCHEMA`, and `EXECUTE` |
| MCP call returns HTTP 503 | Target MCP App status | Make sure the MCP App is running and the supervisor links the correct App name |
| Browser page does not load | App status and Logs tab | Check `/health`, then read the first startup error in Logs |
| Memo appears without a trace | Trace request/UI state | Run from the App UI; the UI requests `debug_trace=true` automatically |
| No response from an old terminal test | Local shell tooling or expired token | Use the browser UI; this guide intentionally does not require terminal authentication |
| Bootstrap overwrote sample rows | `INSERT OVERWRITE` in the SQL | Treat the bootstrap as synthetic POC setup; do not run it on shared data without agreement |

When diagnosing deployment, inspect the App’s **Logs** tab first. The most
useful startup clues are missing resource keys, invalid `app.yaml` syntax,
dependency installation failures, and permission errors.

## Final success checklist

You are finished with the UI-only POC when all of these are true:

- [ ] The custom App `insurance-fraud-supervisor-poc` exists.
- [ ] The App deploy source is the Git repository with source path `custom_agent`.
- [ ] The SQL warehouse is linked as `supervisor-warehouse` with **Can use**.
- [ ] The MLflow experiment is linked as `supervisor-experiment`.
- [ ] The model endpoint is linked as `supervisor-model` with **Can query** and is READY.
- [ ] The MCP App is linked as `supervisor-mcp-app` with **Can use** and is RUNNING.
- [ ] All twelve UC functions are linked with **Can execute**.
- [ ] The App status is **RUNNING**.
- [ ] The browser demo returns a memo for `CLM-1001`.
- [ ] The memo shows the safe trace diagram.
- [ ] The missing-claim test asks for a claim identifier without querying claim data.
- [ ] The optional evaluation job, if created, reports a contract pass rate of `1.0`.

## Which repository files matter for this UI workflow?

| File | Use it for |
|---|---|
| `custom_agent/app.yaml` | Custom App startup command and UI resource bindings |
| `custom_agent/server/agent.py` | Bounded supervisor loop and Responses API |
| `custom_agent/server/ui.py` | Browser memo and trace diagram |
| `custom_agent/server/uc_tools.py` | Parameterized UC function calls |
| `custom_agent/server/mcp_tools.py` | App-to-App MCP connection |
| `custom_agent/server/plane_registry.py` | Allowlisted planes and routing validation |
| `sql/bootstrap.sql` | Synthetic tables, rows, and UC functions |
| `app/app.yaml` | Separate MCP App configuration; do not use for supervisor deployment |
| `eval/evaluate_supervisor.py` | Optional Jobs UI evaluation harness |
| `eval/test_cases.json` | Synthetic evaluation contract cases |
| `resources/*.yml` | Optional automation definitions; not required for this UI-only guide |
| `databricks.yml` | Optional bundle configuration; not required for this UI-only guide |

## Optional native Supervisor comparison

If you also want to compare the native Databricks experience:

1. Open the **Agents** area in Databricks.
2. Choose **Create Agent**.
3. Choose **Supervisor Agent** if that option is available.
4. Add the appropriate tools or subagents and provide the instructions from
   `supervisor/instructions.md`.

That creates a separate native Agent Bricks object. It does not deploy the
custom LangGraph code, the document-style UI, or the `/responses` API from this
repository. Keep it separate from `insurance-fraud-supervisor-poc`.

## Official Databricks references

- [Create a custom Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/create-custom-app)
- [Deploy a Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy)
- [Add resources to a Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)
- [Define environment variables in a Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/environment-variables)
- [Add a UC function resource](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/functions)
- [Add a model serving endpoint resource](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/model-serving)
- [Run multi-statement queries in SQL Editor](https://docs.databricks.com/aws/en/sql/user/sql-editor/run-queries)
- [Configure and edit Lakeflow Jobs](https://docs.databricks.com/aws/en/jobs/configure-job)
- [Use Git with Lakeflow Jobs](https://docs.databricks.com/aws/en/jobs/git)
- [Configure the serverless environment](https://docs.databricks.com/aws/en/compute/serverless/dependencies)
- [Configure Python script task parameters](https://docs.databricks.com/aws/en/jobs/task-parameters)
- [Create MLflow experiments](https://docs.databricks.com/aws/en/mlflow/experiments)
- [Evaluate GenAI Apps with an MLflow harness](https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/concepts/eval-harness)
