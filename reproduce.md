# Reproduce the custom supervisor in the Azure Databricks UI

Last reviewed: 2026-08-28

This guide assumes you are starting in another Azure Databricks workspace, do
not have the Databricks CLI, and will manually upload the agent code. It creates
the supervisor App first and links teammate-owned resources afterward.

Do not paste access tokens into the code or App settings. Your browser login is
used while you configure the App. At runtime, the App uses its own Databricks
service principal and only the resources linked on its **App resources** page.

## Before you start

You need:

1. The `custom_agent` folder from this repository on your computer.
2. Access to the target Azure Databricks workspace in a browser.
3. Permission to create a Databricks App and upload files to a workspace
   folder.
4. Permission to link, or help from owners who can link, the resources listed
   in Step 4.

You do not need GitHub. Azure hosting does not prevent manual workspace-folder
deployment.

## Step 1 — Create the custom App shell

1. Open your Azure Databricks workspace URL.
2. Sign in normally.
3. In the left sidebar, click **Databricks Apps**. If the sidebar is collapsed,
   first open the app switcher in the upper-left.
4. Click **Create app**.
5. Select **Create a custom app**. Do not select an Agent Bricks chatbot or
   supervisor template; this repository supplies its own Python supervisor.
6. Enter an App name, for example:

   ```text
   insurance-fraud-supervisor-poc
   ```

7. Enter a description such as:

   ```text
   Development-only bounded supervisor for insurance-fraud triage.
   ```

8. Continue to the source or Git configuration screen.
9. Choose **Skip**, **Configure later**, or the equivalent option that creates
   the App without a Git provider.
10. Leave automatic deployment off.
11. Click **Create app**.
12. Wait until the App overview page appears.

If there is no way to skip Git, ask a workspace administrator whether the Apps
setting **Only allow app deployments from Git** is enabled. That policy must be
changed, or an approved Azure DevOps repository must be supplied, before you
can use manual upload. This is a workspace policy, not a limitation of Azure.

The App does not need to be running yet. Creating it now gives you the App
identity that will receive resource permissions.

## Step 2 — Prepare the code folder

The folder you deploy must have `app.yaml` at its top level. Confirm this shape
on your computer:

```text
custom_agent/
├── app.yaml
├── pyproject.toml
├── requirements.txt
└── server/
    ├── __init__.py
    ├── agent.py
    ├── mcp_tools.py
    ├── plane_registry.py
    ├── start_server.py
    ├── uc_tools.py
    ├── vector_tools.py
    └── ui.py
```

Do not upload the repository root as this App’s source. The `app/` directory is
a separate MCP server, and the older `sql/` and bundle files are not required
for this deployment.

If your workspace import screen accepts a ZIP, compress the contents of
`custom_agent` so that opening the ZIP immediately shows `app.yaml`. Avoid an
extra nested `custom_agent/custom_agent` directory.

## Step 3 — Upload the code without a Git provider

1. In Azure Databricks, click **Workspace** in the left sidebar.
2. Open your user folder under **Users**.
3. Click **Create → Folder**.
4. Name it:

   ```text
   insurance-fraud-supervisor-poc
   ```

5. Open the folder.
6. Use **Import**, **Upload**, or the three-dot menu, depending on your UI.
7. Upload the prepared ZIP, or upload `app.yaml`, `pyproject.toml`, and
   `requirements.txt`, then create/upload the `server` folder and its files.
8. Confirm that `app.yaml` is directly inside the workspace folder you will
   select as the App source.
9. Open `app.yaml` in the Databricks editor and confirm that it contains these
   resource bindings:

```yaml
command: ["uv", "run", "start-server"]

env:
  - name: WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: MLFLOW_TRACKING_URI
    value: databricks
  - name: MLFLOW_REGISTRY_URI
    value: databricks-uc
  - name: MODEL_ENDPOINT
    valueFrom: LLM
  - name: MCP_APP_NAME
    valueFrom: ontobricks_kg
  - name: CLAIM_TABLE
    valueFrom: claim_360
  - name: PARTY_TABLE
    valueFrom: party_360
  - name: LOCATION_TABLE
    valueFrom: location_360
  - name: POLICY_TABLE
    valueFrom: policy_360
  - name: VECTOR_SEARCH_INDEX
    valueFrom: vector-search-index
  - name: VECTOR_SEARCH_COLUMNS
    value: chunk_id,chunk_to_retrieve,source_path,document_type
  - name: VECTOR_SEARCH_QUERY_COLUMNS
    value: chunk_to_embed
  - name: CLAIM_FRAUD_METRICS_TABLE
    valueFrom: claim_fraud_metrics
```

The right side of each `valueFrom` line must exactly match an App resource key
created in the next step. Keys are case-sensitive; `LLM` is uppercase.
The two Vector Search column settings are plain values, not resource keys. Do
not add `db_chunk_to_embed_vector` to the returned columns.

## Step 4 — Link the current resources

1. Return to **Databricks Apps**.
2. Open the App created in Step 1.
3. Open **Configure**, **Settings**, or **App resources**.
4. Click **Add resource** once for each row below.

| Add this type | Select this resource | Permission | Resource key |
|---|---|---|---|
| Databricks app | `mcp-ontobricks-07x` | **Can use** | `ontobricks_kg` |
| UC table | `dmpipeline-dev.ri_gold.claim_360` | **Can select** | `claim_360` |
| UC table | `dmpipeline-dev.ri_gold.party_360` | **Can select** | `party_360` |
| UC table | `dmpipeline-dev.ri_gold.location_360` | **Can select** | `location_360` |
| UC table | `dmpipeline-dev.ri_gold.policy_360` | **Can select** | `policy_360` |
| Serving endpoint | `databricks-claude-opus-5` | **Can query** | `LLM` |
| AI Search index | `dmpipeline-dev.plane4.chunks_demo_index` | **Can select** | `vector-search-index` |
| UC table | `dmpipeline-dev.ri_gold.claim_fraud_metrics` | **Can select** | `claim_fraud_metrics` |

For each resource:

1. Choose the type in the first column.
2. Use the picker to find the exact resource in the second column.
3. Choose the permission in the third column.
4. Type the resource key in the fourth column.
5. Save or add the resource.
6. Check the completed list before adding the next one.

If a resource does not appear, do not substitute a similarly named resource.
Ask its owner or a workspace administrator to confirm that it exists in this
workspace and that you may grant it to the App identity.

## Step 5 — Understand the SQL warehouse gap

The eight original resources are not enough to issue SQL statements against
the five UC tables. Add the warehouse before deploying the current source,
because `app.yaml` now requires the `sql-warehouse` resource key.

`Can select` is data authorization. A SQL warehouse is the compute that
executes the query. The supervisor handles this safely: when no warehouse is
linked, it records each direct table plane as unavailable instead of crashing
the server.

To turn on direct table reads:

1. Open the App’s **App resources** page.
2. Click **Add resource**.
3. Choose **SQL warehouse**.
4. Select a running or auto-starting serverless SQL warehouse approved for the
   POC.
5. Choose **Can use**.
6. Set the resource key to:

   ```text
   sql-warehouse
   ```

7. Save the resource.
8. Open the uploaded `app.yaml`.
9. Confirm these two lines already exist under `env`:

   ```yaml
     - name: WAREHOUSE_ID
       valueFrom: sql-warehouse
   ```

10. Redeploy in Step 7.

If the team truly cannot provide a SQL warehouse for this POC, leave the code
as-is. The app remains usable, but any answer must disclose that direct table
evidence was unavailable.

## Step 6 — Confirm identifiers used by your tables

The default claim format is `CLM-1001`, and the two baseline tables are
expected to contain a `claim_id` column. The supervisor reads table metadata at
runtime and only uses relationship columns that actually exist.

Default relationship candidates are:

| Plane | Candidate columns, in order |
|---|---|
| `claim_profile` | `claim_id` |
| `fraud_metrics` | `claim_id` |
| `party_profile` | `party_id`, `claimant_party_id`, `insured_party_id`, `claim_id` |
| `location_profile` | `location_id`, `loss_location_id`, `address_id`, `claim_id` |
| `policy_profile` | `policy_id`, `claim_id` |

The baseline claim row is queried first. IDs found in that evidence can then be
used to query party, location, and policy tables. If your actual column names
are different, use the dynamic configuration procedure in Step 10 instead of
editing query logic.

If claim IDs follow a different pattern, add plain values to `app.yaml`, for
example:

```yaml
  - name: CLAIM_ID_REGEX
    value: '\bAZ-[0-9]{8}\b'
  - name: CLAIM_ID_EXAMPLE
    value: AZ-00001234
```

## Step 7 — Deploy the App from the workspace folder

1. Return to **Databricks Apps** and open your App.
2. Click **Deploy** or **Create deployment**.
3. For source type, choose **Workspace folder**.
4. Browse to the folder uploaded in Step 3.
5. Select the folder whose top level contains `app.yaml`.
6. Confirm the deployment.
7. Watch the deployment status and logs.
8. Wait for the App status to become **Running**.

The first build installs `uv`, resolves the Python dependencies from
`pyproject.toml`, and starts the MLflow Responses Agent server. It can take a
few minutes.

If the deployment reports that a `valueFrom` key cannot be resolved, compare
every key in Step 3 with the App resource list in Step 4. The most common error
is a capitalization or hyphen mismatch.

## Step 8 — Run the browser demo

1. On the App overview page, click **Open app**.
2. Wait for the supervisor page to load.
3. Enter a real POC claim ID using a request such as:

   ```text
   For CLM-1001, give me a concise fraud-risk triage summary and explain which resources were consulted.
   ```

4. Click **Generate memo**.
5. Read the answer.
6. Expand **Supervisor orchestration trace**.
7. Verify that the diagram shows decision, query, and synthesis steps.
8. Check each resource status.

Expected behavior without a warehouse:

- the App itself loads;
- the model can route and synthesize;
- `document_search` can query the linked AI Search index when selected;
- `knowledge_graph` can discover tools from `mcp-ontobricks-07x` when selected;
- direct table planes say `unavailable` and identify `WAREHOUSE_ID` as missing.

Expected behavior after a warehouse is linked:

- `claim_profile` and `fraud_metrics` show `query_table` operations;
- related planes run when the router needs them and a usable relationship ID
  was found;
- the trace includes row counts and the exact linked resource name.

## Step 9 — Pin the intended Ontobricks MCP tool if needed

The supervisor first calls MCP `list_tools()`. It can automatically call a tool
only when the tool looks read-only and all required inputs map to the claim ID
or user question.

If the trace says `missing_configuration`:

1. Expand the raw trace.
2. Find `available_tools` under `knowledge_graph`.
3. Ask the Ontobricks owner which listed tool is the intended read-only query.
4. Confirm its required arguments through the MCP tool schema or owner.
5. Add this plain environment value to `app.yaml`:

   ```yaml
     - name: MCP_TOOL_NAME
       value: exact_read_tool_name
   ```

6. Save and redeploy.

Do not pin a create, update, delete, insert, or other write-capable tool for the
automatic triage loop.

## Step 10 — Add another resource later

Suppose the team adds
`dmpipeline-dev.ri_gold.provider_360`.

1. Open the App’s **App resources** page.
2. Add it as a **UC table** with **Can select**.
3. Set its resource key to `provider_360`.
4. Add this binding to `app.yaml`:

   ```yaml
     - name: PROVIDER_TABLE
       valueFrom: provider_360
   ```

5. Add or update this configuration value under `env`:

   ```yaml
     - name: SUPERVISOR_RESOURCE_CONFIG_JSON
       value: '{"planes":[{"name":"provider_profile","description":"Related provider details.","kind":"table","env_var":"PROVIDER_TABLE","lookup_columns":["provider_id","claim_id"]}]}'
   ```

6. Save and redeploy.
7. Ask a provider-related question and verify that the router can select
   `provider_profile`.

An entry with an existing plane `name` overrides that default. Use this to
change lookup columns in another workspace. Supported kinds are `table`,
`vector_search`, and `mcp`.

## Step 11 — Health and frontend endpoints

The browser UI is the simplest demo and uses your logged-in browser session.
For a future application-owned frontend:

- `GET /health` checks whether the App server is available.
- `POST /responses` accepts Responses-Agent requests.
- `custom_inputs.debug_trace=true` returns the safe supervisor trace in
  `custom_outputs.supervisor_trace`.

Do not expose a workspace OAuth token in browser JavaScript. The frontend auth
design should be completed before external users are connected.

## Troubleshooting

| Symptom | Check |
|---|---|
| App shows Service unavailable immediately | Deployment logs; missing `valueFrom` keys; source folder contains `app.yaml` |
| `valueFrom` resolution failed | Match `LLM`, `ontobricks_kg`, `claim_360`, `party_360`, `location_360`, `policy_360`, `vector-search-index`, and `claim_fraud_metrics` exactly |
| Table plane says `WAREHOUSE_ID` missing | Add the optional SQL warehouse in Step 5 and redeploy |
| Table metadata or query is permission denied | Confirm the table is linked with **Can select** and the App identity can use the catalog/schema |
| Related table says `missing_input` | The earlier evidence did not expose a configured relationship ID; check Step 6 |
| AI Search returns unavailable | Confirm the exact index is ONLINE and linked with **Can select** |
| AI Search says `columns` is missing | Upload the current `vector_tools.py`, keep both `VECTOR_SEARCH_*_COLUMNS` settings from Step 3, and redeploy |
| MCP returns HTTP 503 | Open `mcp-ontobricks-07x`, confirm it is Running, then inspect its logs and downstream dependencies |
| MCP lists tools but does not call one | Follow Step 9 and pin the confirmed read-only tool |
| Model query fails | Confirm `databricks-claude-opus-5` is READY and the App has **Can query** |
| App asks for a claim ID you supplied | Adjust `CLAIM_ID_REGEX` to the actual identifier format |

## Final verification checklist

- [ ] The custom App shell exists.
- [ ] The workspace source folder contains `app.yaml` at its top level.
- [ ] All eight current resources are linked with the exact keys in Step 4.
- [ ] The App reaches **Running**.
- [ ] The browser UI opens.
- [ ] A claim request returns a memo and safe trace diagram.
- [ ] MCP tool discovery succeeds, or the intended read-only tool is pinned.
- [ ] The SQL warehouse is linked if direct UC table rows are required.
- [ ] No token, password, or secret is stored in the uploaded source.

## Official references

- [Databricks App resources](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/resources)
- [Add an AI Search index to a Databricks App](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/vector-search)
- [Use MCP servers in custom agents](https://learn.microsoft.com/en-us/azure/databricks/agents/agent-framework/agent-tool)
- [Databricks SQL Statement Execution API](https://learn.microsoft.com/en-us/azure/databricks/sql/api/statements)
