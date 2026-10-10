# Incident Report: Settlement File Delay - January 2025

**Incident ID:** INC-2025-0108
**Severity:** SEV-2
**Date:** 2025-01-08
**Duration:** 6 hours
**Department:** Payments
**Access Level:** internal
**Created Date:** 2025-01-08
**Document Type:** incident

## Summary
Nightly settlement file generation for card transactions delayed by 6 hours due to OOM kills on the reconciliation service.

## Impact
- Settlement to partner banks delayed
- Temporary increase in pending transactions visible to customers
- No financial loss (funds were held correctly)

## Root Cause
Memory leak in the batch processor when handling a new merchant category code mapping file that was 3x larger than previous months. The leak was the same class of issue later seen in March 2025 (INC-2025-0312).

## Recurring Root Causes Identified Across Incidents
1. Connection / resource pool exhaustion after configuration or certificate changes
2. Memory pressure on reconciliation under larger-than-expected batch sizes
3. Idempotency key handling under burst traffic

## Recommendations
- Introduce memory profiling gates in CI for reconciliation
- Cap batch sizes and implement progressive processing
- Shared runbook section for "resource exhaustion" patterns
