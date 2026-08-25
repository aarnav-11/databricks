"""FastAPI and stateless HTTP MCP application."""

from fastapi import FastAPI
from fastmcp import FastMCP

from server.tools import load_tools

mcp_server = FastMCP(name="insurance-fraud-memory")
load_tools(mcp_server)

mcp_app = mcp_server.http_app(stateless_http=True)

health_app = FastAPI(
    title="Insurance Fraud Memory MCP",
    version="0.1.0",
    lifespan=mcp_app.lifespan,
)


@health_app.get("/", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "healthy", "mcp_endpoint": "/mcp"}


combined_app = FastAPI(
    title="Insurance Fraud Memory MCP",
    routes=[*mcp_app.routes, *health_app.routes],
    lifespan=mcp_app.lifespan,
)
