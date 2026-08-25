"""Start the MLflow ResponsesAgent-compatible Databricks App server."""

from pathlib import Path

from dotenv import load_dotenv
from mlflow.genai.agent_server import AgentServer

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

# Importing the module registers the @invoke and @stream handlers.
import server.agent  # noqa: E402,F401

# This App exposes the Responses API directly. There is no embedded chat UI
# yet, so do not proxy browser requests to the unused port 3000.
agent_server = AgentServer("ResponsesAgent")
app = agent_server.app


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "insurance-fraud-supervisor-poc",
        "responses_endpoint": "/responses",
    }


def main() -> None:
    agent_server.run(app_import_string="server.start_server:app")
