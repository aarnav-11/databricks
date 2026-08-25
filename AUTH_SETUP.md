# Databricks POC authentication

This project uses the modern Databricks CLI and Declarative Automation Bundles.
The profile name expected by `databricks.yml` is `POC`.

## 1. Find the workspace URL

Open the target Databricks workspace and copy the base URL from the browser
address bar. It should look like:

```text
https://dbc-xxxxx.cloud.databricks.com
```

Use the workspace URL, not the account-console URL.

## 2. Install the Databricks CLI

On macOS with Homebrew:

```bash
brew install databricks/tap/databricks
databricks version
```

The current CLI supports OAuth user-to-machine authentication and bundle
commands. If Homebrew requires an explicitly trusted tap, use:

```bash
brew tap databricks/tap
brew trust databricks/tap
brew install databricks
```

## 3. Authenticate with OAuth

Run this from the project directory, replacing the placeholder host:

```bash
databricks auth login \
  --host https://<workspace-host> \
  --profile POC
```

Complete the browser sign-in and consent flow as your own Databricks user.
Accept the suggested profile or keep the name `POC`.

OAuth is preferred for this attended local setup. The CLI stores the token in
macOS Keychain; do not paste a token into this repository or into chat.

## 4. Verify authentication without printing secrets

```bash
databricks auth describe --profile POC
databricks auth profiles
databricks current-user me --profile POC
```

`auth describe` should show the workspace host and a successful auth type.
Do not use the `--sensitive` flag.

## 5. Validate this bundle

From `/Users/aarnav/Desktop/Databricks`:

```bash
databricks bundle validate --target dev --profile POC
```

This is a read-only validation step. Do not run `databricks bundle deploy`
until the POC resources have been added and you explicitly want them created.

## Required Databricks-side access for the supervisor POC

The native Supervisor Agent requires a Unity Catalog-enabled workspace,
serverless compute, Model Serving access, a serverless usage policy with a
nonzero budget, and at least one subagent or tool. The user testing the
supervisor must also have access to that subagent or tool.

## References

- https://docs.databricks.com/aws/en/dev-tools/cli/authentication
- https://docs.databricks.com/aws/en/dev-tools/cli/install
- https://docs.databricks.com/aws/en/dev-tools/bundles/reference
- https://docs.databricks.com/aws/en/agents/agent-bricks/multi-agent-supervisor
