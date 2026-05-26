# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x | Yes |

## Design principles

- **No secrets in config files.** Slack tokens, signing secrets, SSH keys, and cloud credentials are always read from environment variables that the config _names_.
- **Lazy imports.** Cloud SDKs are only loaded when actually used — reduces attack surface.
- **Access control by default.** Slack commands are gated per VM — unauthorized users get denied.
- **Signature verification.** All Slack requests are verified using HMAC-SHA256 signing secret.

## Reporting a vulnerability

If you discover a security vulnerability, please do **not** open a public GitHub issue.

Instead, email: **tarunrj99@gmail.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact

You will receive acknowledgment within 48 hours and a resolution timeline within 7 days.
