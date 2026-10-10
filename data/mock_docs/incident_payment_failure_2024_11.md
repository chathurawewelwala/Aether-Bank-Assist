# Incident Report: Intermittent Payment Failures - November 2024

**Incident ID:** INC-2024-1122
**Severity:** SEV-2
**Date:** 2024-11-22
**Duration:** 3 hours 12 minutes
**Department:** Payments
**Access Level:** internal
**Created Date:** 2024-11-22
**Document Type:** incident

## Summary
Intermittent 5xx errors on UPI collect requests. Approximately 18% of UPI transactions failed with "GATEWAY_TIMEOUT".

## Impact
- ~9,200 failed UPI transactions
- Customer NPS drop of 4 points that week
- Affected primarily Android app users on older OS versions

## Root Cause
A race condition in the idempotency key generation logic of the UPI adapter when under high concurrency. Combined with a recent increase in timeout thresholds on the NPCI gateway side.

## Timeline
- 09:15 - Error rate started climbing
- 09:40 - Payments team notified via Slack
- 10:20 - Identified correlation with traffic spike from festival campaigns
- 11:50 - Hotfix deployed for idempotency key uniqueness
- 12:27 - Error rate returned to baseline

## Recurring Themes
Idempotency key collisions also seen during Diwali 2023 campaign.

## Lessons Learned
- Load testing must include realistic concurrency on idempotency paths
- Timeout configuration changes on external gateways require coordinated rollout
