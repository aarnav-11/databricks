"""Run the bounded supervisor against the POC evaluation contract."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--model-endpoint", required=True)
    parser.add_argument("--mcp-app-name", required=True)
    parser.add_argument("--mlflow-experiment-id", required=True)
    return parser.parse_args()


args = _arguments()
os.environ.update(
    {
        "WAREHOUSE_ID": args.warehouse_id,
        "FRAUD_CATALOG": args.catalog,
        "FRAUD_SCHEMA": args.schema,
        "MODEL_ENDPOINT": args.model_endpoint,
        "MCP_APP_NAME": args.mcp_app_name,
        "MLFLOW_TRACKING_URI": "databricks",
        "MLFLOW_REGISTRY_URI": "databricks-uc",
        "MLFLOW_EXPERIMENT_ID": args.mlflow_experiment_id,
        "MLFLOW_GENAI_EVAL_MAX_WORKERS": "1",
        "MLFLOW_GENAI_EVAL_PREDICT_RATE_LIMIT": "0.1",
    }
)

script_name = globals().get("__file__")
search_roots = []
if script_name:
    script_path = Path(script_name).resolve()
    search_roots.extend([script_path.parent, *script_path.parents])
search_roots.extend([Path.cwd(), *Path.cwd().parents])
repo_root = next(
    (
        candidate
        for candidate in search_roots
        if (candidate / "custom_agent" / "server" / "agent.py").exists()
    ),
    None,
)
if repo_root is None:
    raise RuntimeError("Could not locate the bundle root containing custom_agent/server/agent.py")
sys.path.insert(0, str(repo_root / "custom_agent"))

import mlflow  # noqa: E402
from mlflow.entities import Feedback  # noqa: E402
from mlflow.genai.scorers import scorer  # noqa: E402

mlflow.set_tracking_uri("databricks")
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(experiment_id=args.mlflow_experiment_id)

from server.agent import Supervisor, _trace_payload  # noqa: E402


_SUPERVISOR: Supervisor | None = None


def _supervisor() -> Supervisor:
    global _SUPERVISOR
    if _SUPERVISOR is None:
        _SUPERVISOR = Supervisor()
    return _SUPERVISOR


@mlflow.trace(name="supervisor_harness_predict")
def predict(question: str) -> dict[str, Any]:
    state = _supervisor().run(question)
    return {
        "response": state.get("final_text", ""),
        "supervisor_trace": _trace_payload(state),
    }


def _function_names(trace: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for call in trace.get("function_calls", []):
        functions = call.get("functions", []) if isinstance(call, dict) else []
        if isinstance(functions, list):
            names.update(str(name) for name in functions)
        elif functions:
            names.add(str(functions))
    return names


@scorer
def supervisor_contract(
    *,
    outputs: Any = None,
    expectations: dict[str, Any] | None = None,
    **_: Any,
) -> Feedback:
    """Check deterministic safety and orchestration expectations."""

    expected = expectations or {}
    payload = outputs if isinstance(outputs, dict) else {"response": str(outputs or "")}
    response = str(payload.get("response", ""))
    trace = payload.get("supervisor_trace", {})
    if not isinstance(trace, dict):
        trace = {}

    queried_planes = set(trace.get("queried_planes", []))
    function_names = _function_names(trace)
    checks: dict[str, bool] = {
        "trace_present": trace.get("type") == "safe_orchestration_trace",
        "claim_id": not expected.get("claim_id") or trace.get("claim_id") == expected["claim_id"],
        "required_planes": set(expected.get("required_planes", [])).issubset(queried_planes),
        "required_functions": set(expected.get("required_functions", [])).issubset(function_names),
        "required_text": all(text.lower() in response.lower() for text in expected.get("required_text", [])),
        "stop_reason": not expected.get("expected_stop_reason")
        or trace.get("stop_reason") == expected["expected_stop_reason"],
        "no_function_calls": not expected.get("no_function_calls") or not trace.get("function_calls"),
    }
    passed = all(checks.values())
    failed = [name for name, check in checks.items() if not check]
    rationale = "All contract checks passed." if passed else f"Failed checks: {', '.join(failed)}."
    return Feedback(value=passed, rationale=rationale)


def main() -> None:
    cases_path = repo_root / "eval" / "test_cases.json"
    evaluation_data = json.loads(cases_path.read_text())
    result = mlflow.genai.evaluate(
        data=evaluation_data,
        predict_fn=predict,
        scorers=[supervisor_contract],
    )

    metrics = {str(key): float(value) for key, value in result.metrics.items()}
    contract_metric = next(
        (value for key, value in metrics.items() if key.startswith("supervisor_contract")),
        None,
    )
    summary = {
        "run_id": result.run_id,
        "case_count": len(evaluation_data),
        "metrics": metrics,
        "contract_pass_rate": contract_metric,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if contract_metric is None or contract_metric < 1.0:
        raise SystemExit("Supervisor evaluation contract failed")


if __name__ == "__main__":
    main()
