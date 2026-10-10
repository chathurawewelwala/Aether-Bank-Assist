# Policy: Data Access and Classification

**Document Type:** policy
**Department:** Security
**Access Level:** internal
**Created Date:** 2025-02-01

## Classification Levels
- **Public**: Marketing material, public product docs
- **Internal**: Architecture, runbooks, most incident reports
- **Confidential**: Customer PII, financial positions, board materials
- **Restricted**: Cryptographic keys, privileged credentials

## Access Control Principles
1. Role-based access control (RBAC) enforced at API and data layer
2. Least privilege: default deny
3. All access to Confidential+ must be logged and audited
4. AI assistants must respect the same classification as human users

## AI Assistant Specific Rules
- The Aether Assistant must never return Confidential or Restricted content to Viewer role
- Analyst role may access Internal + aggregated analytics
- Administrator role has full access including tool invocation for diagnostics
- Prompt injection attempts that try to override role restrictions must be blocked and logged
