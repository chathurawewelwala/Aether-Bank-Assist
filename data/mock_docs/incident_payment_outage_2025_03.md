# Incident Report: Payment Gateway Outage - March 2025

**Incident ID:** INC-2025-0312
**Severity:** SEV-1
**Date:** 2025-03-12
**Duration:** 47 minutes
**Department:** Payments
**Access Level:** internal
**Created Date:** 2025-03-12
**Document Type:** incident

## Summary
Complete outage of the primary payment gateway (PayFlow v3) affecting all card and UPI transactions between 14:22 and 15:09 IST.

## Impact
- 12,400 failed transactions
- Estimated revenue loss: ₹2.1 Cr
- Customer complaints: 3,800
- Affected services: Mobile App, Internet Banking, POS terminals

## Root Cause
Cascading failure triggered by a memory leak in the reconciliation microservice after a routine certificate rotation. The leak exhausted the connection pool to the downstream settlement engine.

## Timeline
- 14:22 - First alerts from synthetic monitoring
- 14:25 - On-call engineer paged
- 14:31 - Confirmed SEV-1, war room opened
- 14:48 - Identified connection pool exhaustion
- 15:02 - Rolled back certificate change and restarted pods
- 15:09 - Full recovery confirmed

## Recurring Themes
Similar connection pool exhaustion observed in Jan 2025 (INC-2025-0108) and Nov 2024 after config changes.

## Action Items
1. Implement circuit breakers on settlement connections (Owner: Platform)
2. Add memory leak detection to reconciliation service (Owner: Payments Eng)
3. Certificate rotation runbook update to include pre-flight connection pool checks
