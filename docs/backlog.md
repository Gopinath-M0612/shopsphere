# ShopSphere DevOps Onboarding Backlog

Environments: **dev** = Kubernetes on your laptop (Docker Desktop) · **prod** = AWS EKS (Mumbai, ap-south-1)
Rules: one ticket = one branch (`SS-<n>-short-name`) → commit `SS-<n>: ...` → PR → merge.
Every epic ends with **troubleshooting drills**. A drill is done only when its RCA is in `docs/rca/`.

---

## EPIC 1: Containers
| Ticket | Task | Acceptance criteria |
|---|---|---|
| SS-1 | Read the code (KT) and fill `docs/service-inventory.md`: port, start command, env vars, dependencies, health endpoints per service | Table complete for all 5 services |
| SS-2 | Dockerfile + `.dockerignore` for **catalog** and **orders** (Python) | Non-root user, slim base, image < 250 MB, `/health` ok via `docker run` |
| SS-3 | Dockerfile for **inventory** (Node.js) | `npm ci --omit=dev`, non-root, `/health` ok |
| SS-4 | **Multi-stage** Dockerfile for **gateway** (Go): build stage + tiny runtime stage | Final image < 30 MB, contains binary + `public/` only |
| SS-5 | Dockerfile for **worker** | Non-root, ops port 9100 `/health` ok |
| SS-6 | `platform/compose/compose.yaml`: all 5 services + Postgres (3 databases) + Redis, healthchecks, `depends_on: condition: service_healthy` | `docker compose up` → place an order in the UI → status reaches SHIPPED |
| 🔥 D-1 | **Drills:** wrong `DATABASE_URL` · missing `INTERNAL_API_TOKEN` · port mapping missing · container runs as root | 4 RCAs |

## EPIC 2: Kubernetes (dev)
| SS-7 | Namespace `shopsphere`, Deployments + Services for all 5, ConfigMap per service, Secret for passwords + internal token | All pods `Running`, `kubectl port-forward` to gateway works |
| SS-8 | Postgres as **StatefulSet + PVC**, Redis Deployment | Delete the Postgres pod → orders still there after restart |
| SS-9 | Liveness + readiness probes (correct endpoint per service!), requests/limits | Kill Postgres → catalog/orders go NotReady but are **not** restarted |
| SS-10 | Ingress (`shopsphere.local`) to the gateway | UI opens at `http://shopsphere.local` |
| SS-11 | HPA on catalog + gateway, PodDisruptionBudget, 2 replicas of worker | `loadgen --users 30` → HPA scales up; 2 workers share events without duplicates |
| 🔥 D-2 | **Drills:** CrashLoopBackOff · ImagePullBackOff · readiness probe pointed at `/ready` of a dependency · OOMKilled · Service selector mismatch · wrong ConfigMap key | 6 RCAs |

## EPIC 3: Packaging and delivery
| SS-12 | Helm chart `platform/helm/shopsphere` with `values-dev.yaml`, `values-prod.yaml` | `helm upgrade --install` deploys everything |
| SS-13 | GitHub Actions CI per service: lint → test (with Postgres/Redis service containers) → build → **Trivy scan** → push to GHCR, tag = git SHA | Failing test or HIGH/CRITICAL CVE blocks the PR |
| SS-14 | Argo CD: app-of-apps, auto-sync dev, manual sync prod | Merge to `main` → dev updated without `kubectl` |
| SS-15 | Zero-downtime rollout: `maxUnavailable: 0`, preStop sleep, check graceful shutdown in logs | `loadgen` during rollout → 0 errors |
| 🔥 D-3 | **Drills:** bad image tag rolled out → rollback with Helm/Argo · migration fails on startup · secret rotated but pods not restarted | 3 RCAs |

## EPIC 4: Observability
| SS-16 | kube-prometheus-stack; ServiceMonitors for all 5 `/metrics` | All targets UP in Prometheus |
| SS-17 | Grafana dashboard: request rate, error %, p95 latency per service, outbox pending, worker pending, DLQ size, low-stock SKUs | Dashboard JSON committed |
| SS-18 | Loki + Promtail; find one order's journey across all services by `request_id` | Screenshot/query in runbook |
| SS-19 | Alerts: error rate > 5%, p95 > 1s, outbox pending > 50, DLQ > 0, pod restarts, low stock | Each alert fired once in a drill |
| 🔥 D-4 | **Drills** (use `CHAOS_*` vars): latency spike in catalog · 30% errors in inventory · Redis down (outbox fills up, then drains) · worker dead → events pile up | 4 RCAs, each found via dashboard/alerts first |

## EPIC 5: Security
| SS-20 | RBAC: read-only `developer` role, CI service account limited to its namespace | `kubectl auth can-i` evidence |
| SS-21 | Pod Security `restricted`, `runAsNonRoot`, read-only root FS where possible | Namespace labelled, all pods admitted |
| SS-22 | NetworkPolicies: only gateway → APIs, only orders/worker → inventory, only orders/worker → Redis, DBs only from their service | `curl` from a wrong pod times out |
| SS-23 | External secrets (Sealed Secrets or External Secrets Operator) | No plain secret in Git |

## EPIC 6: AWS prod
| SS-24 | AWS account hardening: IAM admin user + MFA, **budget alarm ₹500** | Budget email received |
| SS-25 | Terraform: remote state (S3 + DynamoDB), VPC, EKS, node group | `apply` builds, `destroy` removes everything |
| SS-26 | ECR repos; CI pushes to ECR via OIDC (no long-lived keys) | Images in ECR |
| SS-27 | RDS Postgres + ElastiCache Redis via Terraform; secrets in AWS Secrets Manager | Services connect, no passwords in Git |
| SS-28 | AWS Load Balancer Controller + Ingress, CloudWatch Container Insights | Public URL works |
| SS-29 | Prod release via Argo CD; **teardown runbook** | Release + rollback + destroy documented |
| 🔥 D-5 | **Drills:** node group scaled to 0 · security group blocks RDS · IAM role missing for LB controller | 3 RCAs |

---

## RCA template (`docs/rca/YYYY-MM-DD-short-title.md`)
```
# <title>
Impact:      who/what was affected, for how long
Detection:   how we noticed (alert, user, dashboard)
Timeline:    hh:mm  event
Root cause:  the real reason (not the symptom)
Fix:         what restored service
Prevention:  what stops it happening again (ticket number)
Evidence:    commands + output that proved it
```
