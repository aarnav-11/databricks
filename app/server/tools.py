"""MCP tools for external evidence and controlled case-memory writes."""

import json
import os
import re
import uuid
from urllib.parse import quote
from urllib.request import Request, urlopen

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def _require_vin(vin: str) -> str:
    normalized = vin.strip().upper()
    if not VIN_PATTERN.fullmatch(normalized):
        raise ValueError("VIN must contain 17 valid VIN characters")
    return normalized


def _require_memory_input(claim_id: str, note: str, source: str) -> tuple[str, str, str]:
    normalized_claim = claim_id.strip().upper()
    normalized_note = note.strip()
    normalized_source = source.strip()
    if not re.fullmatch(r"CLM-[0-9]{4,12}", normalized_claim):
        raise ValueError("claim_id must look like CLM-1001")
    if not normalized_note or len(normalized_note) > 1000:
        raise ValueError("note must contain 1 to 1000 characters")
    if not normalized_source or len(normalized_source) > 64:
        raise ValueError("source must contain 1 to 64 characters")
    return normalized_claim, normalized_note, normalized_source


def load_tools(mcp_server) -> None:
    """Register the POC tools on a FastMCP server."""

    @mcp_server.tool
    def health() -> dict[str, str]:
        """Check that the insurance fraud MCP server is running."""
        return {"status": "healthy", "service": "insurance-fraud-memory"}

    @mcp_server.tool
    def decode_vin(vin: str) -> dict:
        """Decode a vehicle VIN with the public NHTSA vPIC API.

        Use this only to corroborate vehicle identity in an auto claim. External
        data can be incomplete and must not be treated as proof of fraud.
        """
        normalized = _require_vin(vin)
        endpoint = (
            "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"
            f"{quote(normalized)}?format=json"
        )
        request = Request(endpoint, headers={"User-Agent": "databricks-fraud-poc/0.1"})
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.load(response)
        except Exception as exc:
            return {
                "status": "unavailable",
                "vin": normalized,
                "source": "NHTSA vPIC",
                "error": str(exc),
            }

        results = payload.get("Results") or []
        if not results:
            return {"status": "not_found", "vin": normalized, "source": "NHTSA vPIC"}

        decoded = results[0]
        return {
            "status": "ok",
            "vin": normalized,
            "make": decoded.get("Make"),
            "model": decoded.get("Model"),
            "model_year": decoded.get("ModelYear"),
            "vehicle_type": decoded.get("VehicleType"),
            "error_code": decoded.get("ErrorCode"),
            "error_text": decoded.get("ErrorText"),
            "source": "NHTSA vPIC",
        }

    @mcp_server.tool
    def remember_case_note(
        claim_id: str,
        note: str,
        source: str = "supervisor-user-request",
    ) -> dict:
        """Persist a case note to the governed Delta memory table.

        Call this tool only when the user explicitly asks to save a note. This
        tool records context; it does not make or execute a claim decision.
        """
        normalized_claim, normalized_note, normalized_source = _require_memory_input(
            claim_id, note, source
        )
        warehouse_id = os.environ["WAREHOUSE_ID"]
        catalog = os.getenv("FRAUD_CATALOG", "workspace")
        schema = os.getenv("FRAUD_SCHEMA", "insurance_fraud_poc")
        memory_id = f"MEM-{uuid.uuid4()}"

        response = WorkspaceClient().statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            catalog=catalog,
            schema=schema,
            wait_timeout="30s",
            statement=f"""
                INSERT INTO {catalog}.{schema}.case_memory
                  (memory_id, claim_id, memory_type, note, created_at, created_by, confidence)
                VALUES
                  (:memory_id, :claim_id, 'SUPERVISOR_NOTE', :note,
                   current_timestamp(), :source, 1.0)
            """,
            parameters=[
                StatementParameterListItem(name="memory_id", value=memory_id),
                StatementParameterListItem(name="claim_id", value=normalized_claim),
                StatementParameterListItem(name="note", value=normalized_note),
                StatementParameterListItem(name="source", value=normalized_source),
            ],
        )
        payload = response.as_dict()
        state = payload.get("status", {}).get("state")
        if state != "SUCCEEDED":
            return {"status": "failed", "memory_id": memory_id, "details": payload.get("status")}
        return {
            "status": "saved",
            "memory_id": memory_id,
            "claim_id": normalized_claim,
            "created_by": normalized_source,
        }
