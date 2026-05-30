# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.5.x | Yes |
| 1.4.x | Yes |
| 1.3.x | Security fixes only |
| < 1.3 | No |

## Security architecture

### Secrets management
- **No secrets in config files.** Slack tokens, signing secrets, SSH keys, and cloud credentials are always read from environment variables that the config _names_.
- **SSH keys are base64-encoded** when stored as environment variables in serverless deployments.
- **Config files are safe to commit** — they only contain references to env var names, never actual values.

### Request validation
- **Slack signature verification.** All incoming Slack requests are validated using HMAC-SHA256 with the signing secret. Replayed or tampered requests are rejected.
- **Timestamp validation.** Requests older than 5 minutes are rejected (replay attack prevention).

### Access control
- **Per-VM authorization.** Each VM has a `notify_users` / `allowed_users` list. Only listed users can start/stop that VM.
- **Access control modes:** `mentioned_only` (default), `channel_members`, `specific_users`.
- **Unauthorized actions** return an explicit denial message — no silent failures.

### Runtime protection
- **Kill-switch manifest.** The library checks a remote `.manifest.json` on every invocation. If the upstream marks it inactive, all functions stop processing immediately.
- **Lazy imports.** Cloud SDKs are only loaded when actually used — reduces attack surface.
- **No shell injection.** SSH commands use paramiko's exec_command, not shell interpolation.
- **Minimal IAM permissions.** Only `compute.instanceAdmin`, `monitoring.viewer`, and `storage.objectAdmin` are required.

### Supply chain
- **Tag-pinned installs.** Production deployments install from a specific git tag (`@v1.5.1`), not `main`.
- **Dependabot enabled.** Automated dependency updates with vulnerability scanning.
- **No third-party actions with write access.** CI workflows use only official GitHub actions.

### Network security
- **Firewall tags.** VMs use a dedicated `vm-power-manager-ssh` network tag for fine-grained SSH access.
- **No broad SSH exposure.** Only tagged VMs accept connections from the monitoring service.

## Automated scanning

This repository uses:
- **Bandit** — Python static security analysis
- **TruffleHog** — Secret detection in git history
- **Safety** — Known vulnerability checks in dependencies
- **Dependabot** — Automated dependency updates

## Reporting a vulnerability

If you discover a security vulnerability, please do **not** open a public GitHub issue.

Instead, email: **tarunrj99@gmail.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive acknowledgment within 48 hours and a resolution timeline within 7 days.
