# Security model

External content is untrusted. Web pages, messages, PDFs, email, GitHub content, media and transcriptions carry data, never system authority.

Execution path:

AI -> Tool Request -> Policy Engine -> Authorization -> Scoped Credential -> Execution -> Audit.

Mandatory production controls: service identity, least privilege, short-lived credentials, private Cloud SQL networking, TLS, egress restrictions, rate limits, audit trails, dependency/SBOM scanning, secret scanning and rollback.

Owner approval remains mandatory for money, material spend, contracts, legal actions, sensitive credentials, high-risk publication, irreversible deletion and irreversible strategic decisions.

The built-in policy layer is a fail-closed application guard. It is not a replacement for OPA/OpenFGA/IAM in production.
