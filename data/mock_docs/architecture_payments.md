# Architecture Document: Payments Platform

**Document Type:** architecture
**Department:** Payments
**Access Level:** internal
**Created Date:** 2024-09-01
**Version:** 3.2

## High-Level Design
Aether Bank Payments Platform is a microservices-based system built on Kubernetes (GKE).

### Core Components
- **API Gateway (Kong)**: External and internal traffic, rate limiting, auth
- **PayFlow Orchestrator**: Core routing and state machine
- **Reconciliation Service**: End-of-day settlement matching
- **UPI Adapter**: NPCI integration
- **Card Processor Adapter**: Visa/MC/RuPay
- **Fraud Engine**: Real-time risk scoring (separate team)

### Data Flow
1. Client request → API Gateway
2. AuthN/AuthZ via Keycloak token validation
3. PayFlow selects processor based on payment method + routing rules
4. Async status updates via Kafka
5. Settlement file generation nightly

### Resilience Patterns
- Circuit breakers (Resilience4j)
- Bulkheads for processor isolation
- Idempotency keys on all mutating endpoints
- Multi-AZ deployment with pod disruption budgets

### Known Bottlenecks
- Reconciliation service memory profile under large batch sizes
- Connection pool sizing to legacy settlement engine (Oracle)
