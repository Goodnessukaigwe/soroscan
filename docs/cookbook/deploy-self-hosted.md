# Deploy Self-Hosted

Run SoroScan in your own environment for full control and private workloads.

## Quick Path

Start with Docker Compose:

- See [Docker Compose Deployment](../deployment/docker-compose.md)
- Then scale with [Kubernetes Deployment](../deployment/kubernetes.md)

## Production Checklist

- Configure persistent Postgres and Redis volumes.
- Put API behind TLS and an ingress controller.
- Set alerting for worker lag and API error rates.
- Back up database snapshots on a schedule.
