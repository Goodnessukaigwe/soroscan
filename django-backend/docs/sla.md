# SoroScan Service Level Agreement (SLA)

## Overview

This document defines the availability, recovery, and performance targets for the SoroScan platform.

## Availability Targets

| Tier | Uptime Target | Measurement Window |
|------|--------------|-------------------|
| API  | 99.9%        | Rolling 30 days   |
| Indexer | 99.5%    | Rolling 30 days   |
| Webhooks | 99.0%   | Rolling 30 days   |

## Recovery Objectives

| Metric | Target | Description |
|--------|--------|-------------|
| RTO (Recovery Time Objective) | < 5 minutes | Time to restore service after primary region failure |
| RPO (Recovery Point Objective) | < 1 minute | Maximum data loss window during failover |

## Database Replication

- PostgreSQL streaming replication to standby region with lag target < 1 minute
- Read replicas distribute query load across regions
- Automatic failover triggers when primary becomes unreachable for > 30 seconds
- Daily backups stored in secondary region with 30-day retention

## Backup Strategy

- Full database backup: daily at 02:00 UTC
- WAL archiving: continuous, streamed to S3 cross-region
- Event archive: S3 gzip batches via `archive_old_events` Celery task (daily)
- Backup verification: weekly restore test in staging environment

## Failover Automation

- Health checks run every 10 seconds via `/api/ingest/health/`
- Kubernetes liveness and readiness probes configured on all deployments
- Automatic region switch on primary outage (target: < 5 minutes)
- DNS failover via Route 53 health checks (TTL: 60 seconds)

## Chaos Engineering

- Monthly chaos tests simulate: primary DB failure, Redis outage, worker crash
- Results tracked in incident log; failures trigger SLA review
- Runbooks maintained in `docs/runbooks/`

## Webhook Delivery SLA

- Target: 95% of webhook deliveries acknowledged within 30 seconds
- Dead-letter queue retains failed deliveries for 30 days for manual replay
- Escalation policy: Slack (2 failures) → SMS (4 failures) → PagerDuty (6 failures)

## Monitoring

- Prometheus metrics exposed at `/metrics`
- Grafana dashboards track: delivery latency, SLA compliance %, budget utilisation
- Alertmanager fires PagerDuty on SLA breach

## Exclusions

- Scheduled maintenance windows (announced 48 hours in advance)
- Force majeure events
- Issues caused by third-party Stellar RPC providers

---
*Last updated: 2026-04-27 | Closes #343*
