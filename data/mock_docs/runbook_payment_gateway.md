# Operational Runbook: Payment Gateway (PayFlow)

**Document Type:** runbook
**Department:** Payments
**Access Level:** internal
**Created Date:** 2025-01-15
**Last Updated:** 2025-06-01

## Overview
PayFlow is Aether Bank's primary payment orchestration layer. It routes card, UPI, netbanking and wallet transactions to respective processors.

## Health Checks
- Endpoint: GET /internal/health/payflow
- Expected: {"status":"healthy","pool_utilization":<0.7,"latency_p99":<120}
- Alert threshold: pool_utilization > 0.85 for 2 consecutive minutes

## Common Failure Modes
1. Connection pool exhaustion to settlement engine
2. Certificate expiry on mTLS channels
3. NPCI / card network latency spikes
4. Idempotency key collisions under high concurrency

## Recovery Procedures

### Connection Pool Exhaustion
1. Check current pool stats: `kubectl exec -it deploy/payflow -- curl localhost:9090/metrics | grep pool`
2. If utilization > 90%: scale replicas temporarily `kubectl scale deploy/payflow --replicas=12`
3. Restart reconciliation sidecar pods
4. Investigate recent config or cert changes

### Certificate Rotation
Always perform pre-flight:
- Verify new cert is loaded in secret
- Run connection test job before applying
- Monitor pool metrics for 15 minutes post-rotation

## Escalation
- SEV-1: Page Payments On-Call + Platform SRE
- SEV-2: Slack #payments-incidents
