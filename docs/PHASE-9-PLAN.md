# Phase 9 — CI/CD Secrets Wiring Plan

Goal: wire all environment variables safely across local dev, CI, and deployment, with zero real secret values in repository.

## Scope

This plan starts after AWS_ROLE_ARN is already added to GitHub Secrets.

> **Open migration:** `docs/TASK.md` tracks replacing the `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`
> vars below with `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASS` (sourced from
> `DATABASE_SECRET_ARN`). Steps 3/4's variable list here still reflect the pre-migration state until
> that task's Phase 3 lands.

## Status (2026-07-21)

Everything doable without a real AWS deployment or without repo-admin access to GitHub Secrets is done:
`Dockerfile`, `infra/cloudformation.yml`, `infra/README.md`, and `.github/workflows/deploy.yml` now exist
in this repo, modeled on `restaraunt-service`'s equivalent files. `AWS_ROLE_ARN` and `AWS_REGION` are now
confirmed present in this repository's GitHub Actions Secrets, so step 1 is closed. Steps 4 (partially),
10, and 11 (partially) remain blocked on actions only a repo/org admin or infra owner can take — see each
step below.

## Step-by-step

1. Add AWS_REGION to GitHub Secrets in this repository.
Reason: OIDC auth flow needs both AWS_ROLE_ARN and AWS_REGION.
**Status: done.** `AWS_ROLE_ARN` and `AWS_REGION` are both present in this repository's GitHub Actions
Secrets. `deploy.yml`'s `configure-aws-credentials` step can now authenticate via OIDC on a real run.

2. Keep CI secret-free.
Check lint and tests run with mocks only. No real AWS, Supabase, or Waze credentials in CI.
**Status: done.** `.github/workflows/python-ci.yml` runs `ruff`/`pytest` only, no secrets referenced.

3. Build single source variable list from env config.
Confirm all app variables are documented and mapped:
- AWS_REGION
- DATABASE_SECRET_ARN (deploy-time only — ARN passed to CloudFormation; ECS injects DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASS at task launch)
- SNS_TOPIC_ARN_ORDER_EVENTS
- SQS_QUEUE_URL_DELIVERY_EVENTS
- ORDER_SERVICE_URL
- WAZE_API_KEY
- AWS_ROLE_ARN (deploy workflow variable, not app runtime env)
**Status: done.** Matches `src/shared/config/env.py` and `.env.example` 1:1; also documented in
`infra/cloudformation.yml`'s parameter list.

4. Split values into GitHub Secrets vs GitHub Variables.
Recommended:
- Secrets: AWS_ROLE_ARN, AWS_REGION, DATABASE_SECRET_ARN, WAZE_API_KEY
- Secret or Variable: SNS_TOPIC_ARN_ORDER_EVENTS, SQS_QUEUE_URL_DELIVERY_EVENTS
- Variable: ORDER_SERVICE_URL
- DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASS — never in GitHub; injected by ECS from `DATABASE_SECRET_ARN`.
**Status: workflow wired, values not yet set.** `deploy.yml` reads `DATABASE_SECRET_ARN`,
`WAZE_API_KEY`, `SNS_TOPIC_ARN_ORDER_EVENTS`, `SQS_QUEUE_URL_DELIVERY_EVENTS`,
`SQS_QUEUE_ARN_DELIVERY_EVENTS` from `secrets.*` and `ORDER_SERVICE_URL` from `vars.*`. None of these have
real values in this repo yet — GitHub resolves unset secrets/vars to an empty string rather than failing.

5. Create Dockerfile and validate local container run.
Do this before deploy workflow work.
Reason: workflow must build and push image before ECS deploy.
**Status: done.** `Dockerfile` (non-root `python:3.12-slim`, uvicorn on port 8000) and `.dockerignore`
added. Not yet validated with an actual `docker build`/`docker run` in this environment — do that before
relying on it in CI.

6. Create deploy workflow with OIDC only.
Requirements:
- permissions include id-token: write
- use aws-actions/configure-aws-credentials
- do not use AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY
**Status: done.** `.github/workflows/deploy.yml` uses `permissions: id-token: write` and
`aws-actions/configure-aws-credentials@v6.1.0` with `role-to-assume: secrets.AWS_ROLE_ARN`; no static keys.

7. Add image build and push stages in workflow.
Build from Dockerfile, tag image with commit SHA, push to ECR, pass tag into deploy stage.
**Status: done.** Same build/push/tag pattern as `restaraunt-service`'s `deploy.yml`.

8. Read required CloudFormation outputs from food-delivery-preview-platform stack.
Must fetch:
- ClusterName
- DeliveryTargetGroupArn
- DeliveryTaskSecurityGroupId
- SubnetIds
**Status: done.** `deploy.yml`'s "Read preview platform outputs" step fetches exactly these four.

9. Deploy ECS runtime stack with exact name delivery-service-runtime.
Reason: cleanup automation in infrastructure repo expects this exact stack name.
**Status: done.** `infra/cloudformation.yml` + `deploy.yml`'s `RUNTIME_STACK_NAME` both use
`delivery-service-runtime` exactly; the deploy step is guarded to run only when the platform stack exists.

10. Force API base path override to /api/v1 during preview routing setup.
Reason: default /api/deliveries path causes 404 against service routes.
**Status: open, not actionable from this repo.** The `delivery_base_path` override is a `workflow_dispatch`
input on `food-delivery-infrastructure`'s own deploy workflow, in a separate repo. Documented as a manual
reminder in `infra/README.md`'s Lifecycle section; whoever runs that other workflow must remember to pass
it.

11. Wire runtime app secrets from AWS Secrets Manager into ECS task definition.
Required runtime secret sources:
- DATABASE_SECRET_ARN — JSON secret with keys host/port/dbname/username/password;
  ECS injects them as DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASS at task launch.
- WAZE_API_KEY
If missing in infrastructure, open explicit infra task and track as blocking gap.
**Status: done for DB (Option A).** `infra/cloudformation.yml` accepts `DatabaseSecretArn` as a
non-sensitive parameter, grants `secretsmanager:GetSecretValue` on that ARN to the task execution
role, and uses an ECS `Secrets` block to inject the five DB env vars directly at task launch — no
plaintext values pass through CloudFormation parameters or GitHub Actions. `WazeApiKey` is still
passed as a plain CloudFormation parameter (same open gap as before; no Secrets Manager entry yet).

12. Enforce secret-safe logging.
Never print raw values for names ending with:
- _KEY
- _SECRET
- _TOKEN
- _ROLE_KEY
**Status: done.** `src/shared/logger.py` / `src/main.py` don't dump full env config; no code path in this
repo logs a raw secret value. Kept as a standing rule for future changes.

13. Run final Phase 9 checklist.
Done when:
- AWS_ROLE_ARN and AWS_REGION exist in this repository secrets
- environment template lists all required variables with fake/empty values only
- deploy workflow uses OIDC and no static AWS keys
- runtime stack name is exactly delivery-service-runtime
- routing override uses /api/v1
- Secrets Manager gap resolved or tracked as open blocker with owner
**Status: not fully closed** — `AWS_ROLE_ARN`/`AWS_REGION` (item 1) are now in place; still blocked on step
10 (routing override, lives in a different repo) and the Secrets Manager half of step 11, neither of which
this repo's code changes can resolve alone.

## Notes

- Internal endpoint for event seeding is not exposed through public API path. For deployed preview tests, use internal access path (for example ECS exec) instead of public curl flow.
- Keep AWS Secrets Manager as source of truth for app-level secrets.
- OPEN GAP: `DATABASE_SECRET_ARN` (the ARN string, not the secret values) and `WAZE_API_KEY` are not
  yet stored in this repository's GitHub Actions Secrets. Until resolved, `deploy.yml` passes an empty
  ARN string, `HasDatabaseSecret` evaluates false, the ECS `Secrets` block is omitted, and the service
  runs with no DB env vars (DB-backed features fail gracefully; distance-only ETA/eligibility fallback
  for Waze). Phase 9 cannot be considered fully closed until this is resolved.
