# Team rules

1. One ticket = one branch: `git checkout -b SS-<n>-<short-name>`
2. Commit messages start with the ticket: `SS-<n>: <what changed>`
3. Open a PR to `main` and fill the template. Self-review against the ticket's acceptance criteria.
4. **Never commit secrets.** Passwords and tokens go in Kubernetes Secrets / AWS Secrets Manager.
5. Every incident or drill gets an RCA in `docs/rca/` (template in `docs/backlog.md`).
6. AWS resources are created **only with Terraform** and destroyed after each practice session.
7. Do not change application code under `services/*/app`, `src`, `worker` or `*.go` (that's the dev team's).
   DevOps files only: Dockerfiles, `.dockerignore`, `platform/`, `infra/`, `.github/`, `docs/`.
