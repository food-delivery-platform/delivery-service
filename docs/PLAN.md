# Delivery Service — Build Plan

> For agents picking up this repo. Read `docs/ARCHITECTURE.md` §0 (Integration Addendum) first — it
> records where this repo's contracts disagree with `order-service` and the platform docs, and which
> side of each disagreement to build against. This plan assumes those decisions.

## Current state (2026-07-16)

The repo is scaffold-only (per `docs/TASK.md`): FastAPI app boots, routers are wired, DTOs/enums exist,
but every route handler returns hardcoded/fake data with `# TODO` markers, and `repository/`, `service/`,
`consumer/`, `publisher/` folders are empty (`__init__.py` only). No AWS/Supabase/Waze client is actually
implemented — `shared/aws/*.py` and `shared/db/supabase_client.py` exist but are not yet called from any
route. Nothing in this plan should be treated as "already working."

Verify this snapshot is still accurate before starting — grep `# TODO` in `src/` and check whether
`repository/`/`service/` files exist yet; another agent may have already completed a phase below.

## Phase-independent ground rules

- Keep DTOs camelCase over the wire (Pydantic `alias` + `populate_by_name`), snake_case internally — this
  is already the pattern in `modules/deliveries/api/dtos.py` and `modules/events/model/order_event.py`.
  Follow it everywhere.
- Every inbound event/request handler must be **idempotent** — check current stored state before acting.
  No message ordering or exactly-once delivery is assumed (§0.2).
- Don't call out to Order Service via REST to push status — only publish SNS events (§0.6).
- Don't write to any table not listed in "Data Stores Used" in `ARCHITECTURE.md` §15.5 plus the new
  `delivery_assignments` table from §0.7. In particular, never write to `active_orders` or
  `order-status-live` — those belong to Order Service.
- Log with `loguru` at the levels already modeled in `deliveries.py` (DEBUG for the 5s/30s poll endpoints,
  INFO for state-changing calls, SUCCESS/WARNING for terminal outcomes) — don't downgrade this.
- **Secrets never live in this repo.** Local dev reads them from a gitignored `.env` (Phase 1 adds
  `.env.example` as the template). In CI/CD they come from **GitHub Actions Secrets**, which are
  themselves a synced copy of **AWS Secrets Manager** (the actual source of truth, per platform
  `ARCHITECTURE.md` §8) — see Phase 9 for the full mapping. Never log a raw secret value, and never add a
  secret's real value to any file this plan asks you to create.

---

## Phase 1 — Shared AWS/DB clients

**Goal:** make `shared/aws/dynamodb_client.py`, `shared/aws/sns_client.py`, `shared/aws/sqs_client.py`,
and `shared/db/supabase_client.py` real, thin wrappers other modules can import.

> **Open migration:** `docs/TASK.md` tracks replacing `supabase_client.py` (PostgREST over
> `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`) with a direct Postgres client driven by
> `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASS`. Not started yet — the `supabase_client.py`
> description below still reflects the current (pre-migration) state.

- `dynamodb_client.py`: boto3 resource/client factory reading `AWS_REGION` from `shared/config/env.py`;
  expose `get_table(name: str)` returning a `Table` resource. No business logic here.
- `sns_client.py`: boto3 SNS client + a `publish(topic_arn: str, subject: str, message: dict)` helper that
  JSON-serializes the message. No FIFO-specific params (`MessageGroupId`/`MessageDeduplicationId`) unless
  Phase 4 confirms FIFO is real — keep the helper signature flexible enough to add them later without a
  breaking change (optional kwargs).
- `sqs_client.py`: boto3 SQS client + `receive_messages(queue_url, max_messages, wait_seconds)` and
  `delete_message(queue_url, receipt_handle)` wrappers.
- `shared/db/supabase_client.py` (now a direct Postgres client — see `docs/TASK.md`; the
  original `supabase-py` factory has been replaced with `psycopg_pool.ConnectionPool`).
- Add `shared/errors/app_error.py` usage consistently (it exists — check it's actually raised/caught, not
  just defined) and a FastAPI exception handler in `main.py` that maps `AppError` → the `api_response.py`
  error envelope.
- Add a `.env.example` at the repo root (doesn't exist yet — `README.md`'s "Getting Started" already tells
  developers to `cp .env.example .env`, but there's nothing to copy). List every variable from
  `shared/config/env.py` with an empty or obviously-fake value — never a real one. This file becomes the
  reference Phase 9 maps to GitHub Actions Secrets.

**Definition of done:** each client can be imported and instantiated with env vars unset without raising at
import time (fail lazily, on first use) — this keeps local dev / tests from requiring real AWS creds.

---

## Phase 2 — Couriers module (GPS + profile)

**Goal:** implement `modules/couriers/` end to end; it's the simplest module and unblocks Phase 3.

- `model/courier_state.py` — confirm it matches `docs/data-model/dynamodb/courier-states.md`
  (`courierId, status, currentOrderId?, vehicleType?, lastLocation?, updatedAt`).
- `repository/` (new file, e.g. `courier_state_repository.py`) — `upsert_location(courier_id, lat, lng, ts)`
  using `UpdateItem` (not full `PutItem`, to avoid clobbering `status`/`currentOrderId` — see write-trigger
  table in `delivery-service-message-contracts.md` §5); `get(courier_id)`; `set_status(courier_id, status,
  current_order_id=None)`.
- `service/` — thin orchestration over the repository; this is where the GPS handler's business logic
  lives (currently the route in `couriers.py` — check its current contents before assuming it's still a
  stub).
- Wire `PATCH /api/v1/couriers/{courierId}/gps` to actually call the repository. Match
  `courier-frontend`'s real client (`gpsApi.ts`): request body is `{lat, lng, timestamp}`, response is an
  empty body — `README.md` says `204`, `delivery-service-message-contracts.md` says `200` with empty body;
  **use 204** (matches the more specific, more recently-written README) and update the contracts doc to
  match if you touch it.
- Add the internal `GET /api/v1/couriers/{courierId}/profile` endpoint (called by Order Service's
  Assignment Engine consumer, per contracts §4) even though nothing calls it yet — it's cheap and unblocks
  Phase 4 without a round trip to User Service being wired first (stub the name/phone lookup against
  Supabase `couriers`/`users` if available, else return `null` fields rather than fabricating data).

**Definition of done:** `PATCH /gps` persists to a local/mocked DynamoDB (see Phase 6 for test setup) and
`GET /courier_state_repository.get()` reflects it.

---

## Phase 3 — Deliveries module: data model + `delivery_assignments` table

**Goal:** give the deliveries module a real backing store, using the table this repo owns per
`ARCHITECTURE.md` §0.7 — **not** `active_orders`.

- Define `delivery_assignments` (PK `orderId`, no SK) in a new file, e.g.
  `modules/deliveries/model/delivery_assignment.py`:
  ```python
  class DeliveryAssignment(BaseModel):
      order_id: str
      restaurant_id: str
      restaurant_address: DeliveryAddress
      delivery_address: DeliveryAddress
      items: list[dict]              # snapshot from order.preparing, display-only
      eligible_courier_ids: list[str] = []
      assigned_courier_id: str | None = None
      stage: DeliveryStage
      estimated_pickup_time: datetime | None = None
      estimated_delivery_time: datetime | None = None
      assigned_at: datetime | None = None
      picked_up_at: datetime | None = None
      delivered_at: datetime | None = None
      courier_confirmed: bool = False
      customer_confirmed: bool = False
      created_at: datetime
      updated_at: datetime
  ```
- `repository/delivery_assignment_repository.py`:
  - `create(assignment)` — called from the SQS consumer on `order.preparing`.
  - `get(order_id)` — used by `GET /deliveries/{orderId}` and `GET /deliveries/available`.
  - `set_eligible_couriers(order_id, courier_ids)` — Assignment Engine writes here (not `active_orders`).
  - `accept(order_id, courier_id, accepted_at)` — **conditional write**,
    `ConditionExpression=attribute_not_exists(assigned_courier_id)`, raising a distinguishable
    `ConflictError` (subclass of `AppError`, 409) on failure — this is the first-writer-wins mechanism from
    `ARCHITECTURE.md` §15.6.
  - `update_stage(order_id, new_stage, ...)`, `set_courier_confirmed`, `set_customer_confirmed`.
- Update `DeliveryStateResponse` DTO to include `restaurantName`, `restaurantAddress`, `customerAddress`
  (per `ARCHITECTURE.md` §0.8 — courier-frontend already expects these).
- Wire `GET /deliveries/{orderId}` and `GET /deliveries/available` to read from this repository instead of
  returning hardcoded data. `available` still needs to filter by `courierId` extracted from the JWT — if
  auth isn't implemented yet, stub the extraction behind a single function so it's a one-line swap later.

**Definition of done:** an assignment created via a direct repository call in a test is retrievable via both
GET endpoints with the correct shape.

---

## Phase 4 — Inbound events: SQS consumer + Assignment Engine

**Goal:** turn `order.preparing` / `order.cancelled` / `order.status.ready` into real side effects.

- `modules/events/consumer/` — background task started from `main.py`'s `lifespan` (the `# TODO: start SQS
  polling background task` comment marks the spot), polling `SQS_QUEUE_URL_DELIVERY_EVENTS` every
  `SQS_POLL_INTERVAL_SECONDS`. Parse the message body against `OrderPreparingEvent` /
  `OrderCancelledEvent` / `OrderStatusReadyEvent` (`modules/events/model/order_event.py`) keyed on
  `eventType`. Unknown `eventType` → log + delete (don't retry into DLQ forever); malformed payload → let
  it fail so SQS redelivers, up to the DLQ threshold.
- Also keep `POST /internal/events` (`api/routes/events.py`) working against the same handler functions, so
  local testing doesn't require real SQS (this endpoint already exists per `README.md`).
- **Assignment Engine** (`modules/deliveries/service/assignment_engine.py`, new):
  1. On `order.preparing`: create the `DeliveryAssignment` row (Phase 3).
  2. Query Supabase `courier_locations` via PostGIS nearest-20 (needs a Supabase RPC or raw SQL via
     `postgrest`/`supabase-py` — check what `restaraunt-service`/`order-service` use for Supabase access
     patterns for consistency, if anything comparable exists).
  3. Call Waze for each candidate (Phase 5 must exist first, or stub with `MAX_COURIER_DISTANCE_MINUTES`
     fallback distance-only ranking — see the documented Waze-failure fallback in §15.6, and build the
     fallback path first since it has no external dependency).
  4. Write `eligible_courier_ids` via the repository.
  5. Fetch courier profile (Phase 2) for the notification payload — actually, `delivery.courier_assigned`
     fires only once a courier *accepts* (`POST /accept`), not at broadcast time — re-check
     `delivery-service-message-contracts.md` §2 ordering before assuming this step belongs here vs. in the
     accept handler. (It belongs in the accept handler — the assignment engine only sets eligibility.)
  6. On `order.cancelled`: mark the assignment cancelled/release any eligible-but-unaccepted state; no
     event needs to be published back (Order Service already knows it cancelled the order).
  7. On `order.status.ready`: update the assignment's status (mostly informational at this stage; the
     courier who accepted still uses `/stage` to move to `PICKED_UP`).

**Definition of done:** POSTing `events/order-preparing.json` to `/internal/events` results in a
`DeliveryAssignment` row visible via `GET /deliveries/{orderId}`.

---

## Phase 5 — Outbound events: SNS publisher + Waze client

**Goal:** replace the remaining `# TODO`s in `deliveries.py` for accept/stage/confirm-delivery.

- `modules/events/publisher/` — `publish_delivery_event(event)` wrapping `shared/aws/sns_client.py`,
  serializing one of the `DeliveryCourierAssignedEvent` / `DeliveryPickedUpEvent` /
  `DeliveryDeliveredEvent` / `DeliveryFailedEvent` / `DeliveryCourierReassignedEvent` models
  (`modules/events/model/delivery_event.py` — already fully defined, just unused).
- `POST /deliveries/{orderId}/accept`: conditional write (Phase 3) → on success, fetch courier profile
  (Phase 2) → publish `delivery.courier_assigned`. On conflict, return 409 with the
  `ALREADY_ASSIGNED`/`CONFLICT` shape (contracts vs. README disagree on the error code string — prefer
  README's `CONFLICT` since it's the more recently written surface, but confirm nothing downstream already
  depends on `ALREADY_ASSIGNED`).
- `POST /deliveries/{orderId}/stage`: update stage in the repository, write an `order_events` audit row
  (new repository method, table already documented in §15.5), publish the matching
  `delivery.status.picked_up` / `delivery.status.failed` event. **Do not** call
  `PATCH /orders/{orderId}/status` (§0.6).
- `POST /deliveries/{orderId}/confirm-delivery`: set `customer_confirmed`; if `courier_confirmed` is also
  true, transition to `DELIVERED` and publish `delivery.status.delivered` with both confirmation flags and
  `confirmedBy`. If only one side has confirmed, return the current (non-terminal) stage rather than
  faking `DELIVERED` — the current stub always returns `DELIVERED`, which is wrong once real state exists.
- Waze client (`shared/http` or a new `shared/waze/client.py`): wrap the routing endpoint from
  `delivery-service-message-contracts.md` §4 (`GET /deliveries/eta` and per-candidate assignment calls).
  Both call sites must fall back to distance-only estimation on failure/timeout and log
  `WazeApiErrorRate`-relevant events (Phase 7 wires the actual metric).

**Definition of done:** the full `accept → stage(PICKED_UP) → stage(DELIVERED)/confirm-delivery` sequence
against a single `orderId` produces the correct SNS payloads (assert via a mocked SNS client in a test) and
leaves the repository in a consistent terminal state.

---

## Phase 6 — GPS sync scheduler

**Goal:** implement the other `main.py` TODO — the APScheduler job.

- `modules/couriers/service/gps_sync_scheduler.py` — reads all `courier_states` (or just those updated
  since last run, if a GSI/index makes that efficient — `GSI_couriers_by_status` doesn't index on
  `updatedAt` globally, so a full scan every 10 min may be the pragmatic MVP approach; note the cost
  tradeoff in a comment rather than over-engineering an incremental sync now).
  Batch-upsert into Supabase `courier_locations` (PostGIS geometry column) via `supabase_client.py`.
- Start it from `main.py`'s `lifespan` using `APScheduler`'s `AsyncIOScheduler`, interval
  `GPS_SYNC_INTERVAL_SECONDS`. Stop it cleanly on shutdown (the existing `# TODO: graceful shutdown`
  comment marks the spot).
- Emit `GpsSyncJobFailureCount` on failure (ties into Phase 7).

**Definition of done:** running the app locally with a mocked Supabase client shows the sync job firing on
the configured interval in logs, and a forced exception is caught and logged rather than crashing the
scheduler thread.

---

## Phase 7 — Observability, health, and CloudWatch metrics

- `GET /health` (`api/routes/health.py`) should report per-module readiness matching the shape in
  `delivery-service-message-contracts.md` §3 (`sqs_consumer`, `assignment_engine`, `gps_sync_scheduler`,
  `waze_client`) — wire real readiness flags (e.g., "has the SQS consumer completed its first successful
  poll") rather than a static `"ok"`.
- Add a thin `shared/metrics/cloudwatch.py` wrapping `PutMetricData` for the six metrics in
  `delivery-service-message-contracts.md` §6 (`CourierAssignmentLagSeconds`, `UnacceptedOrdersCount`,
  `StageMachineErrorCount`, `GpsSyncJobFailureCount`, `WazeApiErrorRate`, `EligibleCouriersFound`). Emit
  from the call sites established in Phases 4–6, not as an afterthought bolted onto `main.py`.

---

## Phase 8 — Tests

No `tests/` directory exists yet in this repo (unlike `order-service`, which already has one — mirror its
convention: `tests/unit/`, `tests/fixtures/events/` seeded from the existing `events/*.json`).

- Unit tests per repository method (conditional-write conflict path is the highest-value test — it's the
  correctness-critical first-writer-wins mechanism).
- Unit tests for the SQS consumer's dispatch-by-`eventType` logic, including the "unknown event type"
  path.
- Contract test: every payload in `events/*.json` parses successfully against its corresponding Pydantic
  model — this catches drift the moment someone edits one side without the other.
- Add a `pytest` + CI step to `.github/workflows/python-ci.yml` (currently ruff-only, per the existing
  workflow file — check it before assuming test running isn't already there).

---

## Phase 9 — CI/CD secrets wiring

**Goal:** make sure every environment variable this service needs is sourced correctly per environment,
without a real secret value ever landing in this repo.

**Status update (2026-07-16): the shared AWS infrastructure now exists as a real, separate repo —
[`food-delivery-infrastructure`](https://github.com/food-delivery-platform/food-delivery-infrastructure).**
It already provisions a permanent VPC/network, permanent Cognito + API Gateway (HTTP API with a JWT
authorizer), and an on-demand *temporary* preview environment (ECS cluster, internal ALB, target groups,
API Gateway routes) sized for exactly two services today: `delivery-service` and `restaurant-service`. This
replaces the hypothetical secrets model below with a concrete one — read this before building any deploy
workflow here.

**Three tiers, same variable names throughout (`shared/config/env.py` is the single list):**

1. **Local dev** — a gitignored `.env` copied from `.env.example` (Phase 1). Values are whatever the
   developer's own sandbox/staging AWS or Supabase project uses.
2. **CI** (`.github/workflows/python-ci.yml`) — the existing lint/format job needs **no real secrets** and
   should stay that way. Tests added in Phase 8 must run against mocked clients (`moto` for boto3, a fake
   Supabase client) rather than real credentials — a lint/test job should never need a secret just to run.
3. **Deployment** (no deploy workflow exists in *this* repo yet, but the pattern to copy already exists in
   `food-delivery-infrastructure/.github/workflows/deploy-eventbridge-preview.yml`) — that workflow
   authenticates with exactly two GitHub Actions secrets:
   - `AWS_ROLE_ARN` — an IAM role assumed via OIDC (`aws-actions/configure-aws-credentials@v6.2.2`,
     `permissions: id-token: write`, **no static access keys**). Copy this pattern exactly; don't introduce
     long-lived `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` secrets when this repo gets its own workflow.
   - `AWS_REGION` — plain region string.
   GitHub Actions secrets are configured **per repo** — `food-delivery-infrastructure` having these set does
   not make them available here. This repo needs its own `AWS_ROLE_ARN`/`AWS_REGION` secrets added (or the
   org needs to switch to org-level shared secrets — that's a GitHub-org-admin decision, not something this
   repo's code can do). **AWS Secrets Manager remains the source of truth** for app-level secrets like
   `SUPABASE_SERVICE_ROLE_KEY`/`WAZE_API_KEY` (per platform `ARCHITECTURE.md` §8) — but as of this writing,
   **`food-delivery-infrastructure` does not yet define any AWS Secrets Manager secrets or ECS `secrets`
   blocks for delivery-service's app config.** That's a real, currently-open gap — flag it to whoever owns
   that repo rather than assuming it already exists.

**What deploying this service into the shared preview environment actually requires** (this repo has no
deploy workflow yet — this is the plan for when one is written, modeled on
`deploy-eventbridge-preview.yml`):

1. Assume the same `AWS_ROLE_ARN` OIDC role, then read four outputs from the **already-deployed**
   `food-delivery-preview-platform` CloudFormation stack via
   `aws cloudformation describe-stacks --stack-name food-delivery-preview-platform --query "Stacks[0].Outputs[...]"`
   (these outputs have no `Export` name, so they must be read this way, not via `Fn::ImportValue`):
   `ClusterName`, `DeliveryTargetGroupArn`, `DeliveryTaskSecurityGroupId`, `SubnetIds`.
2. Deploy this service's own ECS Fargate service + task definition as a **new** CloudFormation stack named
   **exactly `delivery-service-runtime`** — that name is hardcoded into the infra repo's cleanup Lambda
   allow-list (`food-delivery-infrastructure/infrastructure/cleanup.yml`); any other name won't be found or
   auto-deleted, and will linger (and keep costing money) after the preview's `lifetime_minutes` expires.
3. **Path-prefix mismatch to fix before this can work at all:** `preview-platform.yml`'s
   `DeliveryServiceBasePath` parameter defaults to `/api/deliveries`, but this service's actual FastAPI
   prefix (`src/main.py`) is `/api/v1` (`deliveries`/`couriers` routers both mounted under it). Unless the
   API Gateway route is deployed with `delivery_base_path` explicitly overridden to `/api/v1` when someone
   runs `deploy-eventbridge-preview.yml`, every request the ALB forwards will 404 against this service's
   actual routes. This is a deploy-time **input**, not a code change — no FastAPI code needs to move — but
   it's easy to forget since `/api/deliveries` is the workflow's default.
4. `/internal/events` (used to seed test deliveries, see `HELP.md` §6) and the bare `/health` are **not**
   reachable through the API Gateway route at all under this scheme — only `/api/v1/*` is proxied. `/health`
   still works because the ALB target group's own health check calls the container directly, bypassing
   API Gateway routing entirely. `/internal/events` being unreachable externally is arguably correct (it's
   explicitly an internal-testing endpoint) but means seeding a delivery against a *deployed* preview stack
   needs a different mechanism (e.g. `aws ecs execute-command` into the running task) than the simple `curl`
   that works against a local `uvicorn` instance.
5. App-level secrets (`SUPABASE_SERVICE_ROLE_KEY`, `WAZE_API_KEY`, `SUPABASE_URL`) still need somewhere to
   come from at container start — normally an ECS task-definition `secrets` block pulling ARNs out of AWS
   Secrets Manager. Nothing in `food-delivery-infrastructure` creates those secrets yet (point 3 tier above)
   — this repo's own future task-definition stack will likely need to create them, or coordinate with
   whoever owns the infra repo to add them there instead.

**Variable → secret mapping** (updated with the two now-confirmed-real secret names):

| `env.py` variable | GitHub Actions secret? | Sensitive? |
|---|---|---|
| `AWS_REGION` | **secret** `AWS_REGION` (confirmed convention — see `food-delivery-infrastructure`'s workflows) | No |
| `AWS_ROLE_ARN` *(new — not in `env.py` today, needed for the deploy workflow itself)* | **secret** `AWS_ROLE_ARN`, OIDC-assumed | Yes (an ARN isn't secret-secret, but treat it as one — same as the infra repo does) |
| `SUPABASE_URL` | secret (varies per environment) | No (URL only, but still per-env) |
| `SUPABASE_SERVICE_ROLE_KEY` | secret — **no AWS Secrets Manager entry exists for this yet, see above** | **Yes** |
| `SNS_TOPIC_ARN_ORDER_EVENTS` | secret or variable (per-env ARN) | No |
| `SQS_QUEUE_URL_DELIVERY_EVENTS` | secret or variable (per-env URL) | No |
| `ORDER_SERVICE_URL` | variable | No |
| `WAZE_API_KEY` | secret — **no AWS Secrets Manager entry exists for this yet, see above** | **Yes** |

- Never log a raw secret value — if a startup/debug log ever dumps config, redact anything ending in
  `_KEY` / `_SECRET` / `_TOKEN` / `_ROLE_KEY`.
- Follow `food-delivery-infrastructure`'s own IAM policy
  (`iam/github-actions-eventbridge-platform-policy.json`) as the template for scoping this repo's own
  deploy-role permissions narrowly (CloudFormation + the specific ECS/ELB/EC2/logs actions needed) rather
  than granting broad `*` access.

**Definition of done:** `.env.example` exists and lists every variable above; no real secret value appears
anywhere in this repo's git history; `AWS_ROLE_ARN`/`AWS_REGION` secrets exist in *this* repo (not just
`food-delivery-infrastructure`); a deploy workflow (when written) deploys a stack named exactly
`delivery-service-runtime` and passes `delivery_base_path=/api/v1` to the platform stack; the
Supabase/Waze secrets gap is either resolved in AWS Secrets Manager or explicitly still tracked as open.

---

## Phase 10 — Cross-repo confirmation pass (do last)

Before wiring any of this against real staging AWS resources:

- Confirm with the order-service owner whether the courier-search trigger event is `order.preparing` or
  `order.confirmed` (§0.4), and whether SNS/SQS is Standard or FIFO (§0.2).
- Confirm the `delivery.status.*` event shape (per-stage vs. generic `delivery.status_changed`, §0.5) before
  order-service builds its consumer — this repo's shape is richer and should be the one that wins, but it
  needs to be said out loud, not assumed.
- Re-check `courier-frontend/docs/COURIER_APP_ARCHITECTURE.md` for any other response-shape expectations
  beyond §0.8's finding, since that repo's client code is the most concrete/ahead of the other frontends on
  this integration.
- Confirm the `delivery_base_path=/api/v1` override (Phase 9, point 3) with whoever runs
  `food-delivery-infrastructure`'s `deploy-eventbridge-preview.yml` workflow before relying on a deployed
  preview stack for testing — it's a manual `workflow_dispatch` input, easy to leave at its `/api/deliveries`
  default by accident.

---

## Definition of done (whole plan)

- [x] All routes in `api/routes/` call real repository/service code — zero `# TODO` markers left in
      `src/api/` and `src/modules/*/service/`. (Verified 2026-07-16: `grep -rn TODO src/` is empty.)
- [x] SQS consumer and GPS sync scheduler both start from `main.py`'s lifespan and stop cleanly.
- [x] `delivery_assignments`, `courier_states`, `order_events` are the only DynamoDB tables written by this
      service; nothing writes to `active_orders` or `order-status-live`. (`DYNAMODB_TABLE_ACTIVE_ORDERS`
      was removed from `env.py` in Phase 3 — nothing in this repo references either table.)
- [x] No outbound `PATCH /orders/{orderId}/status` REST call exists anywhere in the codebase.
- [x] `GET /deliveries/{orderId}` returns `restaurantName`/`restaurantAddress`/`customerAddress`.
- [x] `.env.example` exists and matches `shared/config/env.py`; no real secret value exists anywhere in
      this repo's git history; the GitHub Actions Secrets ↔ AWS Secrets Manager mapping (Phase 9) is
      documented for whoever builds the deploy workflow (this file's own Phase 9 section).
- [ ] If/when a deploy workflow exists: it deploys a stack named exactly `delivery-service-runtime` and
      passes `delivery_base_path=/api/v1` to `food-delivery-infrastructure`'s preview platform stack.
      **Not done** — writing a real ECS/CloudFormation deploy workflow needs concrete stack outputs from
      `food-delivery-infrastructure` and `AWS_ROLE_ARN`/`AWS_REGION` secrets provisioned in *this* repo
      (a GitHub-admin action), neither of which a repo-only agent can do without real infra access and
      explicit authorization. Left as open, matching this section's own "if/when" framing.
- [x] `tests/` exists and runs in CI.
- [x] `docs/ARCHITECTURE.md` §0 open questions (0.2, 0.4, 0.5) are already resolved with an explicit
      decision recorded in the doc itself (Standard SQS, `order.preparing` as the trigger event, per-stage
      `delivery.status.*` events) — nothing further needed unless order-service disagrees later.
