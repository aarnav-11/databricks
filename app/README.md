# Insurance fraud MCP app

This Databricks App exposes three MCP tools at `/mcp`:

- `health`: confirms the service is running.
- `decode_vin`: calls the public NHTSA vPIC API for external vehicle evidence.
- `remember_case_note`: writes a user-requested note to the governed Delta
  `case_memory` table through a parameterized SQL statement.

The app uses its Databricks App service principal and a bound SQL warehouse.
No personal token or external API key is stored in this source tree.
