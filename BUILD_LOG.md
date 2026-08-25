# Insurance Fraud Memory Layer POC — broad build log

This is the short walkthrough for the POC. It is intentionally broad enough to
read in about 15 minutes. Exact commands and lower-level details live in the
bundle, SQL, app, and supervisor files beside it.

## Goal

Build a development-only insurance fraud assistant on Databricks where a native
Supervisor Agent orchestrates governed Delta knowledge, deterministic rules,
documents, durable memory, and one custom MCP server. The assistant triages and
explains; it never decides whether fraud occurred and never takes adverse action.

## Architecture by plane

| Plane | Databricks artifact | POC behavior |
|---|---|---|
| Entity | `entities` Delta table | Canonical people, claims, policies, vehicles, addresses, providers |
| Knowledge Graph | `graph_edges` + `get_claim_network` UC function | Direct and one-hop relationships with edge evidence |
| Semantic / Structured Knowledge | `claims`, `claim_features` | Normalized claim facts and explainable features |
| Business Knowledge | `business_terms`, `business_rules` | Shared vocabulary and versioned indicator definitions |
| Document | `claim_documents` + `search_claim_documents` | Attributable extracted snippets; lexical search for this small POC |
| Context / Memory | `case_memory` + `get_case_memory` | Prior notes/outcomes; MCP writes only on explicit user request |
| Models / Rules | `model_registry`, `evaluate_claim_rules`, `score_claim` | Transparent deterministic triage score, not a fraud verdict |
| Guardrails / Governance | `governance_policies`, `audit_events`, supervisor instructions | Human-only adverse actions, traceable evidence, injection resistance |
| Orchestration | Native Databricks Supervisor Agent | Selects tools and synthesizes an evidence-led recommendation |

## Tiny insurance dataset

Three synthetic claims make the behavior visible:

- `CLM-1001` is deliberately high risk: new policy, high amount, shared network,
  VIN mismatch, watchlisted repair provider, and multiple recent claims.
- `CLM-1002` is deliberately routine: established policy, low amount, independent
  entities, and documentation aligned with regional norms.
- `CLM-1003` is deliberately ambiguous: reporting delay and a shared provider,
  but insufficient evidence for a conclusion.

All names and facts are synthetic. Document rows are short extracted snippets,
not real files or personal data.

## Tool surface exposed to the supervisor

The Supervisor receives narrow Unity Catalog functions rather than unrestricted
table access:

- `get_claim_snapshot`
- `evaluate_claim_rules`
- `get_claim_network`
- `search_claim_documents`
- `get_case_memory`
- `get_governance_controls`

The custom Databricks App MCP server adds:

- `health`, which verifies the live MCP protocol surface.
- `decode_vin`, which calls the public NHTSA vPIC service.
- `remember_case_note`, which uses parameterized SQL to append memory only after
  an explicit user request.

## Guardrail contract

The supervisor must distinguish facts, deterministic signals, external evidence,
and inference. It cites identifiers, states missing information, recommends the
smallest human review step, and never accuses, denies, prices, pays, closes, or
refers a claim to law enforcement. Documents and memory are evidence, not trusted
instructions.

## Deployment record

- Workspace: `https://dbc-d0355882-ae53.cloud.databricks.com`
- Catalog/schema: `workspace.insurance_fraud_poc`
- Warehouse: `Serverless Starter Warehouse` (`57a8a4c616c87cb2`)
- Supervisor: `insurance-fraud-memory-poc`
  (`29d3abb7-dd82-4035-a295-16a45c08515c`, endpoint
  `mas-29d3abb7-endpoint`)
- Supervisor builder:
  `https://dbc-d0355882-ae53.cloud.databricks.com/ml/bricks/sa/build/29d3abb7-dd82-4035-a295-16a45c08515c?o=7474651884617029`
- MCP app: `mcp-insurance-fraud-poc`
  (`https://mcp-insurance-fraud-poc-7474651884617029.aws.databricksapps.com`)
- Bundle target: `dev`
- Status: deployed and end-to-end verified on 2026-08-21.

### Delta bootstrap verification

The bundle-created job `insurance-fraud-memory-bootstrap` completed successfully:

- Run ID: `892653945246334`
- Run URL:
  `https://dbc-d0355882-ae53.cloud.databricks.com/jobs/109695677377175/runs/892653945246334?o=7474651884617029`
- Created: 11 Delta tables and 7 Unity Catalog SQL functions.
- Seed counts: 16 entities, 17 graph edges, 3 claims, 4 documents, and 3
  memory rows.

The deterministic scorer returned the expected synthetic controls:

| Claim | Score | Tier | Triggered rules |
|---|---:|---|---:|
| `CLM-1001` | 100 | HIGH | 6 |
| `CLM-1002` | 0 | LOW | 0 |
| `CLM-1003` | 35 | MEDIUM | 2 |

### Supervisor and MCP verification

The existing native Supervisor was renamed and given the instructions in
`supervisor/instructions.md`. Its connected tools now include all six read-only
UC functions above, the `mcp-insurance-fraud-poc` App, and the pre-existing
`system.ai.python_exec` tool.

The MCP App deployment reported `SUCCEEDED`; app state is `RUNNING` and compute
state is `ACTIVE`. Direct authenticated MCP checks verified:

- `/` returned a healthy status and advertised `/mcp`.
- `tools/list` returned `health`, `decode_vin`, and `remember_case_note`.
- `health` completed successfully.
- `decode_vin(1HGCM82633A004352)` made a live NHTSA vPIC request and returned a
  2003 HONDA Accord with a clean decode.
- `remember_case_note` was not invoked because no explicit save-note request was
  made.

Two Supervisor endpoint checks then passed:

1. A full `CLM-1001` investigation called all six governed functions, returned
   score 100/HIGH, cited rule, edge, document, memory, and governance IDs, and
   proposed a human vehicle inspection without taking an adverse action. Response
   ID: `resp_4ff8efdd5d9f42b3958a1ac1afa0ac6f`.
2. A focused Supervisor-to-MCP VIN request produced an
   `mcp_approval_request`. After approving only that read-only `decode_vin` call,
   the Supervisor returned the expected NHTSA result. Response ID:
   `resp_f791fa3a85ba4ba9847bcbc43eacf770`.

The MCP approval pause is expected governance behavior. It confirms that an
external MCP execution is not silently performed; the write-capable memory tool
remains gated and unused.

## How to reproduce

```bash
export DATABRICKS_AUTH_STORAGE=plaintext
databricks bundle validate --target dev --profile POC
databricks bundle deploy --target dev --profile POC
databricks bundle run bootstrap_fraud_memory --target dev --profile POC
databricks bundle run fraud_mcp --target dev --profile POC
```

The Supervisor configuration is managed through the `supervisor-agents` CLI
after the UC functions and MCP app exist.

The local `POC` profile uses Databricks OAuth. `DATABRICKS_AUTH_STORAGE=plaintext`
was required only because this automation environment could not access the macOS
Keychain; no access token or client secret is stored in this repository.

## Deliberate POC limits and next production steps

- Lexical document retrieval stands in for chunking, embeddings, and AI Search.
- The graph is represented as governed Delta edges, not a dedicated graph engine.
- The scorer is transparent rules, not a trained fraud model.
- The dataset is tiny, synthetic, and not statistically meaningful.
- Production would add identity resolution, feature pipelines, model monitoring,
  row/column controls, retention, redaction, formal evaluations, and human workflow
  integration.

These limits are intentional: the sample demonstrates the memory architecture
and orchestration pattern without pretending to be a deployable fraud decision system.
