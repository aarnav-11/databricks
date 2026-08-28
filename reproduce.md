# Reproduce the insurance-fraud custom supervisor POC from a clean workspace

Last reviewed: 2026-08-27

This is the literal, beginner-friendly build order. It assumes you have the
repository code but do **not** have any of the Databricks resources from the
original demo.

The guide creates a development-only POC with:

1. Synthetic Unity Catalog tables and governed SQL functions.
2. A custom LangGraph supervisor running as a Databricks App.
3. A small MCP App for VIN corroboration and explicitly requested memory writes.
4. A browser UI that displays a document-style memo and a safe trace diagram.
5. An MLflow evaluation job with three synthetic contract cases.

This guide does **not** create a production deployment. It also does not
require the native Agent Bricks Supervisor. The optional native Supervisor path
is at the end.

## What you are building

```text
Browser UI or your future frontend
              |
              v
Custom Databricks App: /responses
              |
              v
Bounded LangGraph supervisor
       |                    |
       v                    v
UC SQL-function adapters   MCP App adapter
       |                    |
       v                    v
Delta tables/functions     VIN API / explicit memory write

MLflow traces and evaluation results are recorded separately.
```

The Python agent is already written in `custom_agent/server/agent.py`. You do
not paste that Python into a chat box. You deploy the `custom_agent/` folder as
a Databricks App. The `supervisor/instructions.md` file is only for the
optional native Agent Bricks Supervisor described later.

When you finish, the basic success checklist is:

1. The bootstrap job succeeds.
2. The schema contains 11 tables and 12 SQL functions.
3. The MCP App is `RUNNING`.
4. The custom supervisor App is `RUNNING`.
5. The browser UI answers a question about `CLM-1001` and shows the trace path.
6. The evaluation job completes with a contract pass rate of `1.0`.

## Step 1 — Get the Databricks workspace and approvals

### 1.1 Open the workspace

1. Open a browser.
2. Go to the Databricks **workspace URL**, for example:

   ```text
   https://dbc-xxxxxxxx-xxxx.cloud.databricks.com
   ```

3. Sign in with your Databricks user account.
4. If you were given an account-console URL instead of a workspace URL, ask
   your administrator for the workspace URL. The CLI login below needs the
   workspace URL.

### 1.2 Ask an administrator for the following access

You may already have some of this. Do not request production access; ask for a
development workspace or development-only resources.

| Area | What you need | Why |
|---|---|---|
| Workspace | Permission to sign in and use the workspace | Run the CLI and open the UI |
| Unity Catalog | `USE CATALOG` and `CREATE SCHEMA` on the chosen catalog | Create the POC schema |
| POC schema | `USE SCHEMA`, `CREATE TABLE`, and `CREATE FUNCTION` | Run `sql/bootstrap.sql` |
| SQL warehouse | Permission to use an existing warehouse, or permission to create one | Run SQL functions and the bootstrap job |
| Databricks Apps | Apps enabled in the workspace and permission to create/deploy Apps | Host the MCP and custom supervisor Apps |
| Serverless | Serverless Apps/Jobs usage policy with a nonzero budget | Run App and evaluation compute |
| Model Serving | Permission to query a chat-capable model endpoint | The supervisor router and answer writer use the model |
| MLflow | Permission to create or manage your own experiment | Store traces and evaluation results |
| Network | App egress to `*.databricksapps.com` and, optionally, `vpic.nhtsa.dot.gov` | App-to-app MCP calls and VIN lookup |

The bundle grants the App service principals the resource permissions they
need. Your user still needs enough permission to create the resources and run
the bootstrap job. If a deployment says `PERMISSION_DENIED`, copy the exact
resource name from the error and ask the catalog, warehouse, Apps, or model
owner to grant the missing permission.

### 1.3 Confirm that Apps are available

1. In the Databricks workspace, look at the left sidebar.
2. Click the **app switcher** in the upper-left if the sidebar is collapsed.
3. Look for **Databricks Apps**.
4. If it is missing, ask a workspace administrator to enable Databricks Apps
   and serverless compute for the workspace.

Do not continue until you know whether you can create Apps. The code cannot
enable a workspace feature for you.

## Step 2 — Install the local tools

The commands in this guide use a macOS/Linux shell. On Windows, use WSL or
translate the commands to PowerShell.

### 2.1 Install Git

1. Open **Terminal** on macOS/Linux, or **Windows Terminal/WSL** on Windows.
2. Run:

   ```bash
   git --version
   ```

3. If the command is not found, install Git from your operating system's
   package manager, then close and reopen the terminal.

### 2.2 Install the modern Databricks CLI

Use the modern CLI, not the old Python package named `databricks-cli`.

On macOS with Homebrew:

```bash
brew tap databricks/tap
brew trust databricks/tap
brew install databricks
```

On Linux or macOS without Homebrew:

```bash
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
```

On Windows PowerShell:

```powershell
winget install Databricks.DatabricksCLI
```

Close and reopen the terminal, then verify:

```bash
databricks version
```

You need a current CLI. Databricks Apps currently require CLI `0.229.0` or
later, and this repository's bundle App resource syntax needs a CLI that
supports App resources (`0.239.0` or later). If the command prints an older
version, update the CLI before continuing.

### 2.3 Install Python

1. Run:

   ```bash
   python3 --version
   ```

2. Install Python 3.12 or 3.13 if it is missing or the version is outside the
   range `>=3.12,<3.14`.

The deployed App installs its Python dependencies in Databricks. Python is
needed locally for the optional checks and for the JSON output commands in this
guide.

### 2.4 Optional: install `uv` for local App development

You do not need `uv` just to deploy the bundle. Install it if you want to run
the custom App locally:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen the terminal, then verify:

```bash
uv --version
```

## Step 3 — Authenticate the CLI with OAuth

### 3.1 Copy the correct host

1. Return to the Databricks browser tab.
2. Click the browser address bar.
3. Copy only the base workspace URL, such as:

   ```text
   https://dbc-xxxxxxxx-xxxx.cloud.databricks.com
   ```

4. Remove everything after `.com`.
5. Do not copy a URL containing `/sql`, `/ml`, `/jobs`, `/apps`, or a query
   string such as `?o=12345`.

### 3.2 Log in

Replace `<workspace-host>` below with the real host. Do not type the angle
brackets.

```bash
databricks auth login \
  --host https://<workspace-host> \
  --profile POC
```

The command opens a browser. In the browser:

1. Select the same Databricks account you used in Step 1.
2. Approve the CLI sign-in request.
3. Return to the terminal.
4. Keep the profile name `POC` so the commands in this guide work unchanged.

### 3.3 Verify without printing a token

Run each command separately:

```bash
databricks auth profiles
databricks auth describe --profile POC
databricks current-user me --profile POC
```

The last command should show your Databricks username. Never commit a token,
client secret, or `.databrickscfg` file to the repository.

### 3.4 Fix the bundle's workspace host before using it

The checked-in `databricks.yml` contains the original demo workspace as its
default host. You must change it for a different workspace. If you have not
cloned the repository yet, do Step 4 first and then come back here.

1. Open the repository in VS Code or another text editor.
2. Open `databricks.yml`.
3. Find the bottom section:

   ```yaml
   targets:
     dev:
       mode: development
       default: true
       workspace:
         host: https://...
         profile: POC
   ```

4. Replace the `host` value with your workspace host.
5. Leave `profile: POC` if you created the profile with that name.
6. Save the file.

## Step 4 — Put the code on your computer

### 4.1 Clone the repository

If the code is in GitHub, run:

```bash
cd ~/Desktop
git clone https://github.com/aarnav-11/databricks.git
cd databricks
```

If the repository is private, use the HTTPS or SSH clone URL your Git provider
gave you. If you only received a folder of code, copy the complete folder to
your computer and open a terminal in that folder.

### 4.2 Confirm that the folder is complete

From the repository root, run:

```bash
pwd
ls
```

You should see at least these entries:

```text
databricks.yml
sql/
resources/
app/
custom_agent/
eval/
supervisor/
```

If `databricks.yml` is not in the current folder, use `cd` until it is. All
bundle commands must run from the folder containing `databricks.yml`.

### 4.3 Check the local Git state

```bash
git status
```

Stop if you see important uncommitted changes that are not yours. This guide
will edit workspace-specific configuration and you should know which changes
you are making.

## Step 5 — Create or choose the Databricks resources

Write these values down before continuing:

```text
Workspace host:       https://<workspace-host>
CLI profile:          POC
Catalog:              <catalog-you-can-use>
Schema:               insurance_fraud_poc
SQL warehouse ID:     <warehouse-id>
Model endpoint name:  databricks-gpt-oss-120b
MLflow experiment ID: <experiment-id>
MCP App name:         mcp-insurance-fraud-poc
Supervisor App name:  insurance-fraud-supervisor-poc
```

For the first attempt, keep the two App names exactly as shown. App names must
be unique in a workspace, lowercase, and use only letters, numbers, and
hyphens. A clean workspace should not have a collision.

### 5.1 Choose a Unity Catalog catalog

1. In the Databricks browser tab, click **Catalog** in the left sidebar.
2. Look at the catalog list.
3. If `workspace` is present and you can create a schema in it, use:

   ```text
   Catalog: workspace
   ```

4. If `workspace` is not present, choose another catalog where your
   administrator granted you `USE CATALOG` and `CREATE SCHEMA`.
5. Write down the exact catalog name. Catalog names are case-sensitive in
   some contexts and must not include backticks in the bundle variable.

### 5.2 Create the POC schema

If the schema already exists and is dedicated to this POC, you can use it. Do
not reuse a schema that contains unrelated data because the bootstrap script
refreshes the synthetic rows.

1. In **Catalog Explorer**, click your chosen catalog.
2. Click **Create schema**.
3. Enter:

   ```text
   insurance_fraud_poc
   ```

4. Leave the managed storage location blank for this POC unless your
   administrator specifically gave you an external location.
5. Click **Create**.
6. Click the new schema and confirm that it opens.

If **Create schema** is disabled, ask for `USE CATALOG` and `CREATE SCHEMA` on
the parent catalog. SQL warehouses support Unity Catalog, so you do not need to
create a cluster for this step.

### 5.3 Create or choose a SQL warehouse

The bootstrap job and the App use a SQL warehouse. A small serverless warehouse
is sufficient for this synthetic POC.

1. In the left sidebar, click **SQL Warehouses**.
2. Click **Create SQL warehouse**.
3. Enter a name such as:

   ```text
   insurance-fraud-poc-warehouse
   ```

4. Choose **Serverless** if the form offers it.
5. If Serverless is unavailable, choose a **Pro** warehouse and ask your
   administrator whether serverless is enabled. Do not choose a warehouse you
   cannot use.
6. Choose a small cluster size for the POC.
7. Set **Auto Stop** to a short value such as 10 minutes so an idle warehouse
   does not keep consuming compute.
8. Click **Create**.
9. Wait until the warehouse status changes to **Running**.
10. Click the warehouse name and confirm that you can open its details.

Now retrieve the warehouse ID. The ID is not the warehouse display name.

1. Return to the terminal in the repository root.
2. Run:

   ```bash
   databricks warehouses list --profile POC --output json
   ```

3. Find the object whose `name` is the warehouse you just created.
4. Copy its `id` value into your notes as `WAREHOUSE_ID`.

If you already have a running warehouse, you can use its ID instead of creating
another one. It must be a serverless or Pro warehouse that your user can use.

### 5.4 Create the MLflow experiment

The experiment stores custom-agent traces and evaluation runs. You can create
it in the browser:

1. In the left sidebar, click **Workspace**.
2. Open your user folder, usually **Users** → your email address.
3. Right-click the folder or click its kebab menu.
4. Choose **Create** → **MLflow experiment**.
5. Enter a name such as:

   ```text
   insurance-fraud-supervisor-poc
   ```

6. Leave the artifact location blank for this POC.
7. Click **Create**.
8. On the experiment page, click the information icon next to the experiment
   name.
9. Copy the numeric **Experiment ID** into your notes as `EXPERIMENT_ID`.

If your workspace uses the Experiments page instead:

1. Click **Experiments** under **AI/ML** in the left sidebar.
2. Click **New** or **Create experiment**.
3. Choose **Custom**.
4. Enter the same name and create the experiment.
5. Open the experiment information/details menu and copy the Experiment ID.

### 5.5 Check the model endpoint

The custom agent uses a Databricks chat model for two jobs: routing and final
answer synthesis.

1. In the left sidebar, click **Serving**. In some workspaces this is under
   **AI/ML**.
2. Look at the top of the endpoint list for **Foundation Model APIs**.
3. If `databricks-gpt-oss-120b` is listed, use that exact endpoint name.
4. Open the endpoint and confirm that its state is available/ready.
5. If that endpoint is not listed, choose another available **chat-capable**
   Foundation Model API endpoint and write down its exact name.
6. If no model endpoint is available, ask the workspace administrator to
   enable Model Serving/Foundation Model APIs and grant you query access.

You do not need to create an external OpenAI/Anthropic endpoint for this POC.
Using an available Databricks Foundation Model API endpoint avoids adding an
external API key.

## Step 6 — Make the code match your workspace

### 6.1 Use the original namespace if possible

The SQL file in this repository currently uses the literal namespace
`workspace.insurance_fraud_poc`. The easiest first run is therefore:

```text
Catalog: workspace
Schema:  insurance_fraud_poc
```

If you are using those exact names, skip to Step 6.3.

### 6.2 If your catalog is different, update the namespace

If you selected a different catalog, make these edits before deploying. This is
required because the synthetic SQL seed file contains fully qualified table
and function names.

1. In VS Code, press `Cmd+Shift+H` on macOS/Linux or `Ctrl+Shift+H` on Windows
   to open **Find and Replace**.
2. Limit the search to `sql/bootstrap.sql`.
3. In **Find**, enter:

   ```text
   workspace.insurance_fraud_poc
   ```

4. In **Replace**, enter your literal namespace, for example:

   ```text
   main.insurance_fraud_poc
   ```

5. Click **Replace All** for that file only.
6. Open `app/app.yaml`.
7. Change the values next to `FRAUD_CATALOG` and `FRAUD_SCHEMA` to your
   catalog and schema.
8. Open `custom_agent/app.yaml`.
9. Change its `FRAUD_CATALOG` and `FRAUD_SCHEMA` values too. This keeps local
   runs consistent with the deployed run.
10. In the same file, change `MLFLOW_EXPERIMENT_ID` to your experiment ID and
    `MODEL_ENDPOINT` to your selected endpoint. This keeps an optional local
    App run consistent too.
11. Open `databricks.yml`.
12. Change the default values for the `catalog` and `schema` variables, or use
    the `BUNDLE_VAR_...` environment variables in Step 6.3.
13. Save all files.

Do not replace text in source code that is not a catalog/schema reference. The
bundle resource file `resources/custom_agent.app.yml` already uses
`${var.catalog}` and `${var.schema}` for the custom App.

### 6.3 Set the bundle variables for this terminal session

Replace the values below. These are not secrets.

```bash
export BUNDLE_VAR_catalog='workspace'
export BUNDLE_VAR_schema='insurance_fraud_poc'
export BUNDLE_VAR_warehouse_id='<your-warehouse-id>'
export BUNDLE_VAR_model_endpoint='databricks-gpt-oss-120b'
export BUNDLE_VAR_mlflow_experiment_id='<your-experiment-id>'
```

If you selected a different model endpoint, replace the model value with its
exact name. Keep the quotes around values while you are learning; remove the
angle brackets and do not leave spaces in IDs.

Confirm that the values exist without printing secrets (there are no secrets in
these variables):

```bash
printf 'catalog=%s\nschema=%s\nwarehouse=%s\nmodel=%s\nexperiment=%s\n' \
  "$BUNDLE_VAR_catalog" \
  "$BUNDLE_VAR_schema" \
  "$BUNDLE_VAR_warehouse_id" \
  "$BUNDLE_VAR_model_endpoint" \
  "$BUNDLE_VAR_mlflow_experiment_id"
```

These `export` values disappear when you close the terminal. If you open a new
terminal later, set them again or pass the same values with `--var`.

## Step 7 — Validate the bundle before creating anything

1. Make sure you are still in the repository root.
2. Run:

   ```bash
   databricks bundle validate --target dev --profile POC
   ```

3. Confirm that the final line says:

   ```text
   Validation OK!
   ```

This step should not create the Apps or tables. If validation fails, fix the
first error before continuing.

Common validation fixes:

1. `lookup <your-workspace-host>` means you left a placeholder in the host.
2. `profile POC not found` means Step 3 authentication did not finish or used
   another profile name.
3. `unknown variable` means one of the `BUNDLE_VAR_...` names is misspelled.
4. `invalid resource` usually means the modern Databricks CLI is not installed.

## Step 8 — Create the bootstrap job first

The bootstrap job creates the schema objects and synthetic data. Deploying it
first gives the later App resource bindings real UC functions to reference.

### 8.1 Deploy only the bootstrap job

Run:

```bash
databricks bundle deploy \
  --target dev \
  --profile POC \
  --select jobs.bootstrap_fraud_memory
```

If the terminal asks you to approve a development deployment, type `y` and
press Enter. The command should finish without an error.

### 8.2 Run the bootstrap job

```bash
databricks bundle run bootstrap_fraud_memory \
  --target dev \
  --profile POC
```

1. Wait for the command to finish.
2. If it prints a Databricks Jobs URL, save it.
3. Do not start the Apps until the job result is **Succeeded**.

### 8.3 Check the job in the browser

1. Return to the Databricks workspace.
2. Click **Jobs & Pipelines** in the left sidebar.
3. Click **Jobs** if a Jobs/Pipelines selector appears.
4. Search for `insurance-fraud-memory-bootstrap`.
5. Click the job name.
6. Open the newest run.
7. Confirm that the run state/result is **Succeeded**.
8. Click the task output/logs if you want to see the SQL task details.

If the job failed, open the task output and read the first SQL error. The most
common causes are the wrong catalog name, missing schema permissions, or an
unsupported warehouse.

### 8.4 Verify the tables and score in SQL Editor

1. In the Databricks left sidebar, click **SQL** or **SQL Warehouses**.
2. Open **SQL Editor**.
3. In the warehouse selector at the top, choose your POC warehouse.
4. Paste the following query after replacing `C` and `S` with your catalog and
   schema:

   ```sql
   SELECT COUNT(*) AS entity_count FROM C.S.entities;
   SELECT COUNT(*) AS claim_count FROM C.S.claims;
   SELECT * FROM C.S.score_claim('CLM-1001');
   ```

5. Click **Run**.
6. Confirm that the first two queries return nonzero counts.
7. Confirm that the score query returns the seeded `CLM-1001` result: score
   `100`, tier `HIGH`.

The job also creates the remaining tables and functions. The expected table
names are:

```text
entities
graph_edges
claims
claim_features
business_terms
business_rules
claim_documents
case_memory
model_registry
governance_policies
audit_events
```

## Step 9 — Deploy all Apps and the evaluation job

### 9.1 Deploy the full bundle

From the repository root, run:

```bash
databricks bundle deploy \
  --target dev \
  --profile POC
```

This creates or updates:

1. The MCP App `mcp-insurance-fraud-poc`.
2. The custom supervisor App `insurance-fraud-supervisor-poc`.
3. The evaluation job `insurance-fraud-supervisor-evaluation`.

Do not click **Create app** manually for these two Apps when following this
bundle path. The App resources in `resources/fraud_mcp.app.yml` and
`resources/custom_agent.app.yml` create them. Creating blank Apps with the same
names first can cause a name collision during deployment.

It also binds the custom App to:

1. Your MLflow experiment with `CAN_MANAGE`.
2. Your SQL warehouse with `CAN_USE`.
3. Your model endpoint with `CAN_QUERY`.
4. The MCP App with `CAN_USE`.
5. The 12 UC functions with `EXECUTE`.

If the deploy fails while binding a resource, do not manually paste a token
into the App. Fix the named resource permission or ask its owner to grant
access.

### 9.2 Confirm what the bundle created

```bash
databricks bundle summary --target dev --profile POC
```

Look for these resource keys:

```text
Apps:
  fraud_mcp
  supervisor_agent
Jobs:
  bootstrap_fraud_memory
  supervisor_eval
```

The resource key `supervisor_agent` is the custom App even though its display
name is `insurance-fraud-supervisor-poc`.

### 9.3 Start the MCP App

Deploying a bundle creates/updates App configuration but does not necessarily
start the App process. Start it with:

```bash
databricks bundle run fraud_mcp \
  --target dev \
  --profile POC
```

Then check it:

```bash
databricks apps get mcp-insurance-fraud-poc --output json --profile POC
```

In the output, look for:

```text
app_status.state = RUNNING
active_deployment.status.state = SUCCEEDED
```

### 9.4 Start the custom supervisor App

```bash
databricks bundle run supervisor_agent \
  --target dev \
  --profile POC
```

Check its state:

```bash
databricks apps get insurance-fraud-supervisor-poc --output json --profile POC
```

You want:

```text
app_status.state = RUNNING
active_deployment.status.state = SUCCEEDED
```

The App URL is in the same JSON output under `url`. Copy it into your notes as
`APP_URL`. It normally looks like:

```text
https://insurance-fraud-supervisor-poc-<workspace-id>.<region>.databricksapps.com
```

You can also find it in the browser:

1. Click the app switcher in the upper-left.
2. Choose **Databricks Apps**.
3. Click `insurance-fraud-supervisor-poc`.
4. Wait for the deployment to show **Succeeded** and the App to show
   **Running**.
5. Click **Open** or the App URL.

## Step 10 — Use the browser UI

### 10.1 Open the UI

1. Open the `APP_URL` from Step 9.4 in a new browser tab.
2. If Databricks asks you to sign in, sign in with the workspace user who has
   access to the App.
3. You should see the title **Insurance fraud supervisor**.
4. You should see a text box labeled **Investigation request**.

### 10.2 Run the first test

1. Leave the example question in the text box:

   ```text
   For CLM-1001, give me a concise triage summary.
   ```

2. Click **Generate memo**.
3. Wait for the request to finish. The first request can take tens of seconds
   because it calls the model and several SQL functions.
4. Confirm that a document-style memo appears.
5. Under the memo, open **Supervisor orchestration trace** if it is collapsed.
6. Look at the **Trace path** diagram. It should show some combination of:

   ```text
   Request → Decision → Query → Decision → Query → Synthesis
   ```

7. Open the detailed trace cards to see accepted planes, functions, statuses,
   row counts, and stop reason.
8. Open **Raw trace JSON** only if you need the machine-readable payload.

The trace is intentionally a safe orchestration trace. It shows routing and
tool activity; it does not show private model chain-of-thought or hidden
prompts.

### 10.3 Test clarification behavior

1. Replace the question with:

   ```text
   What can you investigate?
   ```

2. Click **Generate memo**.
3. Confirm that the answer asks for a claim identifier such as `CLM-1001`.
4. Confirm that the trace says `missing_claim_id` and does not query claim
   functions.

## Step 11 — Test the API without `jq`

The browser UI is the easiest demo. The API is what your future frontend will
call.

### 11.1 Get a short-lived OAuth token

The CLI can obtain a short-lived token from its OAuth cache. Keep it in the
current process and do not commit it anywhere:

```bash
export DBX_TOKEN="$(databricks auth token --profile POC)"
```

If your shell printed a token while doing this, do not paste it into chat or a
file. It expires and can be revoked, but it should still be treated as secret.

### 11.2 Send a trace-enabled request

Replace `<custom-app-url>` with the App URL from Step 9.4. Do not include a
trailing slash.

```bash
curl --silent --show-error --fail-with-body \
  --request POST \
  "https://<custom-app-url>/responses" \
  --header "Authorization: Bearer ${DBX_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{"input":[{"role":"user","content":"For CLM-1001, give me a concise triage summary."}],"custom_inputs":{"debug_trace":true}}' \
  | python3 -m json.tool
```

`python3 -m json.tool` is used instead of `jq`, so `jq` is not required.

In the JSON response, look for:

```text
custom_outputs.supervisor_trace
```

The trace includes:

1. `claim_id`.
2. `iterations`.
3. `queried_planes`.
4. `function_calls`.
5. `events` containing decision, query, and synthesis records.
6. `stop_reason`.

When finished with the terminal, remove the environment variable:

```bash
unset DBX_TOKEN
```

## Step 12 — Run the MLflow evaluation harness

The repository contains three synthetic cases in `eval/test_cases.json`:

1. A full claim triage case for `CLM-1001`.
2. A missing-claim-ID clarification case.
3. A network-focused case for `CLM-1002`.

The scorer checks the contract around the model: trace presence, claim IDs,
planes, function calls, response language, stop reasons, and clarification
behavior. It does not write case memory.

### 12.1 Run from the terminal

```bash
databricks bundle run supervisor_eval \
  --target dev \
  --profile POC
```

1. Wait for the job to finish; it may take several minutes because it calls the
   model and the governed functions for each case.
2. Confirm the job result is **Succeeded**.
3. Read the output at the end of the run.
4. The expected values are approximately:

   ```text
   case_count: 3
   contract_pass_rate: 1.0
   supervisor_contract/mean: 1.0
   ```

Pydantic serializer warnings can appear with reasoning-capable model output.
They are warnings, not a failed evaluation, if the final job state is
**Succeeded** and the pass rate is `1.0`.

### 12.2 Run from the Databricks UI instead

1. In the workspace, click **Jobs & Pipelines**.
2. Click **Jobs**.
3. Search for `insurance-fraud-supervisor-evaluation`.
4. Click the job name.
5. Click **Run now**.
6. Confirm the run.
7. Wait for the run to show **Succeeded**.
8. Click the task output to read the case count and pass rate.

### 12.3 View evaluation traces in MLflow

1. Click **Experiments** under **AI/ML** in the left sidebar.
2. Open the experiment you created in Step 5.4.
3. Click **Evaluation runs**.
4. Open the newest evaluation run.
5. Confirm that the aggregate contract metric is `1.0`.
6. Click a request identifier to inspect the trace and scorer feedback for an
   individual case.

## Step 13 — Where to change the agent

Use the following map when you begin iterating:

| You want to change | Edit this file |
|---|---|
| Supervisor loop, model router, query budget, synthesis | `custom_agent/server/agent.py` |
| Allowed planes and routing safety checks | `custom_agent/server/plane_registry.py` |
| UC function execution | `custom_agent/server/uc_tools.py` |
| MCP App lookup and VIN call | `custom_agent/server/mcp_tools.py` |
| Browser memo and trace diagram | `custom_agent/server/ui.py` |
| UC tables, seed rows, and SQL functions | `sql/bootstrap.sql` |
| Evaluation cases | `eval/test_cases.json` |
| Evaluation scorer/job runner | `eval/evaluate_supervisor.py` |
| App resource permissions | `resources/custom_agent.app.yml` and `resources/fraud_mcp.app.yml` |
| App startup command/environment | `custom_agent/app.yaml` |
| Native Supervisor instructions | `supervisor/instructions.md` |

After changing custom App code:

1. Save the file.
2. Run local checks if possible.
3. Run `databricks bundle validate`.
4. Run `databricks bundle deploy`.
5. Run `databricks bundle run supervisor_agent` to restart the App.
6. Repeat the browser/API smoke test.
7. Run `databricks bundle run supervisor_eval` for behavioral changes.

Important: `databricks bundle deploy` updates the App configuration and source,
but the App process must be started/restarted with `databricks bundle run
supervisor_agent` before you expect the live URL to serve the new code.

## Step 14 — Optional: create the native Agent Bricks Supervisor

This is a separate product path from the custom App. Use it only if you also
want a native Databricks Supervisor that coordinates UC functions and Apps.
The custom browser UI from Step 10 still calls the custom App, not this native
Supervisor.

### 14.1 Create the native Supervisor

1. Open the Databricks workspace.
2. In the left sidebar, click **Agents**.
3. Click **Create Agent**.
4. Select **Supervisor Agent**.
5. Enter a display name, for example:

   ```text
   Insurance Fraud Native Supervisor POC
   ```

6. Enter a description explaining that it performs synthetic, human-reviewed
   claim triage.

### 14.2 Add the governed functions

In the **Tools and sub-agents** pane:

1. Click **Add** or the tool-type selector.
2. Choose **Unity Catalog function**.
3. Search for and add these read-only functions one at a time:

   ```text
   <catalog>.<schema>.get_claim_snapshot
   <catalog>.<schema>.evaluate_claim_rules
   <catalog>.<schema>.get_claim_network
   <catalog>.<schema>.search_claim_documents
   <catalog>.<schema>.get_case_memory
   <catalog>.<schema>.get_governance_controls
   ```

4. Add a short description to each function so the native Supervisor knows
   when to use it.
5. Do not add a write tool for the first test.

### 14.3 Add the MCP App, if desired

1. In **Tools and sub-agents**, choose **Custom MCP server** or **Databricks
   App**, depending on the label shown in your workspace.
2. Select `mcp-insurance-fraud-poc`.
3. Give it a description such as:

   ```text
   Use only for read-only VIN corroboration when a vehicle VIN is present. Do
   not call the memory write tool unless the user explicitly asks to save a
   note.
   ```

4. Save the tool configuration.

### 14.4 Paste the native instructions

1. Open `supervisor/instructions.md` on your computer.
2. Copy the full file contents.
3. Return to the native Supervisor configuration page.
4. Paste the text into the **Instructions** field.
5. Save or apply the configuration.

The native Supervisor does not automatically read the repository file. You
must paste the text or use the native Supervisor API/CLI to set it.

### 14.5 Grant end-user permissions

1. On the native Supervisor page, open the kebab menu in the upper-right.
2. Click **Manage permissions**.
3. Add yourself or the test user.
4. Grant **Can Query** for normal testing, or **Can Manage** if that user must
   edit the Supervisor.
5. Separately confirm that the same user has `EXECUTE` on each UC function and
   `CAN_USE` on the MCP App.
6. Save the permissions.

### 14.6 Test the native Supervisor

1. Use the right-side chat panel or click **Open in Playground**.
2. Ask:

   ```text
   Investigate synthetic claim CLM-1001 using the governed tools. Return the
   deterministic score, triggered rules, network/document/memory evidence IDs,
   missing information, and the smallest human-review next step. Do not save
   memory or take an adverse action.
   ```

3. Confirm that the answer uses risk-signal language and cites evidence IDs.
4. If an MCP approval prompt appears, approve only the read-only `decode_vin`
   call when you explicitly asked for VIN corroboration.
5. Do not approve `remember_case_note` unless you intentionally asked to save a
   note.

Do not build a new integration on the deprecated Supervisor API. The custom
Databricks App path in this repository is the intended programmable path.

## Step 15 — Troubleshooting

### Error: `lookup <your-workspace-host>: no such host`

Cause: the literal placeholder was sent to the CLI.

Fix:

1. Open `databricks.yml`.
2. Replace the placeholder with the real workspace URL.
3. Make sure the URL begins with `https://`.
4. Remove angle brackets and trailing paths.
5. Re-run `databricks auth login` and `databricks bundle validate`.

### Error: `profile POC not found`

Cause: OAuth login was not completed, or the profile has another name.

Fix:

```bash
databricks auth profiles
databricks auth login --host https://<workspace-host> --profile POC
databricks current-user me --profile POC
```

### Error: `CREATE SCHEMA` or `CREATE TABLE` permission denied

Cause: your user does not own or have create privileges on the chosen catalog/
schema.

Fix: ask the catalog owner/metastore administrator for the exact Unity Catalog
privileges listed in Step 1.2, or select a catalog/schema they have already
prepared for you.

### Error: `function not found` during App deployment

Cause: the bootstrap job did not complete, or the bundle variables point to a
different catalog/schema than the SQL file.

Fix:

1. Check the bootstrap job result.
2. Re-run the SQL verification query.
3. Compare `BUNDLE_VAR_catalog` and `BUNDLE_VAR_schema` with the fully
   qualified names in `sql/bootstrap.sql`.
4. Deploy the full bundle again.

### Error: App resource permission denied

Cause: the App's service principal cannot use the warehouse, query the model,
manage the experiment, use the MCP App, or execute a UC function.

Fix:

1. Open the failed deployment details and identify the resource.
2. In Catalog Explorer, the warehouse permissions page, the model endpoint
   permissions page, or the App permissions page, grant only the permission
   named by the bundle.
3. Re-run the full bundle deploy.

The required App permissions are visible in `resources/custom_agent.app.yml` and
`resources/fraud_mcp.app.yml`.

### Browser says `Service unavailable` or HTTP 503

Cause: the App process is not running, the deployment failed, or the MCP App is
unavailable.

Fix:

1. Run:

   ```bash
   databricks apps get insurance-fraud-supervisor-poc --output json --profile POC
   databricks apps get mcp-insurance-fraud-poc --output json --profile POC
   ```

2. Confirm both Apps are `RUNNING` and their active deployments are
   `SUCCEEDED`.
3. Restart them:

   ```bash
   databricks bundle run fraud_mcp --target dev --profile POC
   databricks bundle run supervisor_agent --target dev --profile POC
   ```

4. Open the App deployment logs in the Databricks Apps page if the state is
   failed.

### Model endpoint not found or not ready

Cause: `MODEL_ENDPOINT` is set to a name that does not exist in the new
workspace, or the App service principal cannot query it.

Fix:

1. Return to Step 5.5.
2. Select an available chat-capable Foundation Model API endpoint.
3. Set `BUNDLE_VAR_model_endpoint` to its exact name.
4. Re-run `databricks bundle validate` and `databricks bundle deploy`.

### MCP returns HTTP 503 or VIN is unavailable

Cause: the MCP App is stopped, or outbound network access to the NHTSA API is
blocked.

Fix:

1. Confirm the MCP App is `RUNNING`.
2. Open the MCP App URL from `databricks apps get` in a browser. Its root
   endpoint should be healthy.
3. Ask the network administrator whether outbound access to
   `https://vpic.nhtsa.dot.gov` is allowed.

The core claim triage still works without VIN corroboration; the trace should
record that external evidence is unavailable.

### `jq: command not found`

You do not need `jq`. Use:

```bash
curl ... | python3 -m json.tool
```

### Evaluation job is slow

The harness makes real model and SQL calls for three cases. Wait for the run to
finish before cancelling it. Warnings about model-output serialization are not
failures by themselves. Read the final job state and contract pass rate.

## Step 16 — Stop or remove the POC

To avoid idle compute charges:

1. Open **Databricks Apps**.
2. Open each POC App.
3. Use the App menu to **Stop** the Apps when you are done.
4. Open **SQL Warehouses**.
5. Stop the POC warehouse.

If you later use `databricks bundle destroy`, read the plan carefully before
confirming. It can remove the bundle-managed Apps and Jobs. The SQL bootstrap
created the tables and functions through SQL, so inspect and remove those
objects separately only when you are certain they contain no needed data.

## Repository source-of-truth map

```text
databricks.yml                       Bundle name, target, variables
resources/setup.job.yml              Bootstrap SQL job
resources/fraud_mcp.app.yml          MCP App and memory-table permission
resources/custom_agent.app.yml       Custom App and all resource bindings
resources/evaluation.job.yml         MLflow evaluation job
sql/bootstrap.sql                    Tables, seed data, and UC functions
app/                                  MCP App source
custom_agent/                        Custom supervisor App source
custom_agent/server/agent.py         LangGraph loop and Responses API
custom_agent/server/ui.py            Memo UI and trace diagram
eval/test_cases.json                 Synthetic evaluation cases
eval/evaluate_supervisor.py          Evaluation runner and scorer
supervisor/instructions.md           Optional native Supervisor instructions
README.md                            Short quick-start
HOW_IT_WORKS.md                      Architecture and table/function mapping
BUILD_LOG.md                         Deployment history and verified IDs
```

## Official Databricks references

The UI labels can move as Databricks evolves. These are the official pages used
to check the current workflow:

1. [Install or update the Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install)
2. [Authenticate the Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/authentication)
3. [Declarative Automation Bundles](https://docs.databricks.com/aws/en/dev-tools/bundles)
4. [Bundle command reference](https://docs.databricks.com/aws/en/dev-tools/cli/bundle-commands)
5. [Set up Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/configure-env)
6. [Create a custom Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/create-custom-app)
7. [Manage Apps with Bundles](https://docs.databricks.com/aws/en/dev-tools/bundles/apps-tutorial)
8. [Add resources to a Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)
9. [Create a SQL warehouse](https://docs.databricks.com/aws/en/compute/sql-warehouse/create)
10. [Create Unity Catalog schemas](https://docs.databricks.com/aws/en/schemas/create-schema)
11. [Unity Catalog privileges reference](https://docs.databricks.com/aws/en/data-governance/unity-catalog/access-control/privileges-reference)
12. [Create foundation model serving endpoints](https://docs.databricks.com/aws/en/machine-learning/model-serving/create-foundation-model-endpoints)
13. [Create MLflow experiments](https://docs.databricks.com/aws/en/mlflow/experiments)
14. [Evaluate GenAI Apps with an MLflow harness](https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/concepts/eval-harness)
15. [Create a native Supervisor Agent](https://docs.databricks.com/aws/en/agents/agent-bricks/multi-agent-supervisor)
