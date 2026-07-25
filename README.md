# delivery-service

Handles the full delivery lifecycle for the Food Delivery Platform: GPS collection, courier proximity assignment, delivery stage transitions, and ETA calculations.

**Runtime:** Python + FastAPI · AWS Fargate (1–4 tasks, auto-scales at 70% CPU)  
**Owned data:** DynamoDB `courier_states`, `delivery_assignments`, `order_events` · Supabase `courier_locations`

---

## Table of Contents

- [Overview](#overview)
- [Why Fargate](#why-fargate)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Internal Modules](#internal-modules)
- [API Reference](#api-reference)
  - [REST Inbound](#rest-inbound)
  - [SQS Inbound — `delivery-events`](#sqs-inbound--delivery-events)
  - [SNS Outbound — `order-events`](#sns-outbound--order-events)
  - [REST Outbound](#rest-outbound)
  - [DynamoDB Write Shapes](#dynamodb-write-shapes)
  - [CloudWatch Custom Metrics](#cloudwatch-custom-metrics)
- [Data Stores](#data-stores)
- [Docker and deployment](#docker-and-deployment)
- [Scaling & Resilience](#scaling--resilience)
- [Environment Variables](#environment-variables)

---

## Overview

The Delivery Service sits between the Order Service and couriers. It receives `order.preparing` events from SQS, finds the best available couriers via PostGIS + Waze, broadcasts available orders for couriers to poll, and tracks every stage until delivery is confirmed by both courier and customer.

```
Order Service (SQS) → [Assignment Engine] → DynamoDB eligible_courier_ids
                                                    ↓
                              Courier App polls GET /api/v1/deliveries/available (30 s)
                                                    ↓
                              Courier taps Accept → conditional DynamoDB write (first wins)
                                                    ↓
                              Stage transitions: ASSIGNED → PICKED_UP → DELIVERED
                                                    ↓
                              SNS order-events → Notification · Monitoring · Order Service
```

---

## Why Fargate

Three constraints make Lambda unsuitable for this service:

1. **In-process GPS sync scheduler** — a background job runs every 10 minutes to batch-sync courier GPS from DynamoDB to Supabase `courier_locations` for PostGIS spatial queries. Lambda's request-scoped model cannot host a recurring in-process job. Python's `APScheduler` runs inside the same uvicorn process.
2. **Waze API call chains** — assigning a courier requires calling Waze once per candidate (up to 20 calls per `order.preparing` event). A warm FastAPI/uvicorn server avoids Lambda cold-start latency on this critical path.
3. **Persistent PostgreSQL connection pool** — PostGIS nearest-courier queries benefit from a warm `asyncpg` connection pool; reconnecting on every Lambda invocation adds measurable latency.

---

## Project Structure

```
delivery-service/
├── requirements.txt
├── README.md
│
├── events/                         # Local test payloads
│   ├── order-preparing.json
│   ├── order-cancelled.json
│   ├── order-status-ready.json
│   ├── accept-delivery.json
│   ├── update-delivery-stage.json
│   └── update-courier-location.json
│
└── src/
    ├── main.py                     # FastAPI app + lifespan (scheduler, SQS consumer)
    │
    ├── api/
    │   └── routes/
    │       ├── deliveries.py       # GET/POST /api/v1/deliveries/*
    │       ├── couriers.py         # PATCH /api/v1/couriers/{id}/gps
    │       ├── events.py           # POST /internal/events (order event processing)
    │       └── health.py           # GET /health
    │
    ├── modules/
    │   ├── deliveries/
    │   │   ├── api/dtos.py         # Pydantic request/response schemas (camelCase JSON)
    │   │   ├── model/
    │   │   │   ├── delivery.py
    │   │   │   ├── delivery_stage.py
    │   │   │   └── delivery_address.py
    │   │   ├── repository/         # DynamoDB + Supabase reads/writes
    │   │   ├── service/            # Assignment engine, stage machine
    │   │   └── validation/
    │   │
    │   ├── couriers/
    │   │   ├── api/dtos.py
    │   │   ├── model/
    │   │   │   ├── courier_state.py
    │   │   │   ├── courier_location.py
    │   │   │   └── vehicle_type.py
    │   │   ├── repository/
    │   │   └── service/
    │   │
    │   └── events/
    │       ├── model/
    │       │   ├── order_event.py  # Inbound SQS event schemas (Pydantic)
    │       │   └── delivery_event.py  # Outbound SNS event schemas
    │       ├── consumer/           # SQS polling background task
    │       └── publisher/          # SNS publish helpers
    │
    └── shared/
        ├── config/env.py           # Environment variables
        ├── aws/
        │   ├── dynamodb_client.py
        │   ├── sns_client.py
        │   └── sqs_client.py
        ├── db/supabase_client.py
        ├── errors/app_error.py
        ├── http/api_response.py    # FastAPI JSONResponse helpers
        └── utils/
```

---

## Getting Started

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment (copy and fill in values)
cp .env.example .env

# 4. Run the development server
uvicorn src.main:app --reload --port 8000
```

Interactive API docs available at `http://localhost:8000/docs`.

---

## Internal Modules

| Module | Trigger | Responsibility |
|--------|---------|----------------|
| **GPS handler** | `PATCH /api/v1/couriers/{id}/gps` every 10 s | Writes courier position to DynamoDB `courier_states.lastLocation` |
| **GPS sync scheduler** | APScheduler in-process job, every 10 min | Reads all active courier GPS from DynamoDB; batch-upserts PostGIS geometry to Supabase `courier_locations` |
| **ETA handler** | `GET /api/v1/deliveries/eta` | Calls Waze for restaurant→customer travel time; returned to Order Service before checkout |
| **SQS consumer** | Background task polling SQS Standard `delivery-events` | Routes `order.preparing` → Assignment Engine; `order.cancelled` → release courier; `order.status.ready` → update broadcast status |
| **Assignment engine** | `order.preparing` event | (1) PostGIS: 20 nearest couriers to restaurant, (2) Waze per courier for arrival time, (3) keep those ≤ threshold, (4) write `eligible_courier_ids` to DynamoDB |
| **Poll handler** | `GET /api/v1/deliveries/available` every 30 s | Returns paid orders for which this courier appears in `eligible_courier_ids` |
| **Accept handler** | `POST /api/v1/deliveries/{id}/accept` | Conditional DynamoDB write (`attribute_not_exists(assignedCourierId)`); 409 if another courier already accepted |
| **Stage state machine** | Courier `POST /stage`; Customer `POST /confirm-delivery` | `ASSIGNED → PICKED_UP → DELIVERED / FAILED`; writes `order_events` audit log; publishes to SNS only — never a REST callback to Order Service |
| **Health check** | `GET /health` | ALB target group readiness probe |

---

## API Reference

### REST Inbound

Exposed via ALB (Fargate target group). Courier App endpoints require `Authorization: Bearer <cognito_jwt>`. Customer App endpoints require a Firebase session cookie verified server-side.

---

#### `PATCH /api/v1/couriers/{courierId}/gps`

Courier App sends GPS position every 10 seconds. Writes to DynamoDB `courier_states.lastLocation`.

**Request body**
```json
{
  "lat": 32.0800,
  "lng": 34.7850,
  "timestamp": "2026-06-28T19:15:00.000Z"
}
```

**Response 204** — no body.

---

#### `GET /api/v1/couriers/{courierId}/profile`

Internal — called by the accept handler (`POST /deliveries/{orderId}/accept`) to populate
`delivery.courier_assigned` with a name/phone/vehicleType. Backed by a direct, best-effort Supabase query
(`couriers` joined to `users`); fields are `null` rather than fabricated if Supabase isn't configured or the
courier isn't found.

**Response 200**
```json
{ "courierId": "courier-001", "name": "Avi Cohen", "phone": "+972501234567", "vehicleType": "bike" }
```

---

#### `GET /api/v1/deliveries/eta`

Called by Order Service at checkout. Returns Waze-calculated restaurant→customer travel time.

**Query params:** `restaurantId`, `deliveryLat`, `deliveryLng`

**Response 200**
```json
{
  "estimatedDeliveryMinutes": 22,
  "restaurantToCustomerKm": 3.1,
  "calculatedAt": "2026-06-28T18:49:00.000Z",
  "source": "waze"
}
```

If Waze is unavailable, `"source": "fallback_distance"` is returned with a distance-based estimate.

---

#### `GET /api/v1/deliveries/available`

Courier App polls every 30 seconds. Courier ID extracted from JWT.

**Response 200**
```json
{
  "availableOrders": [
    {
      "orderId": "order-xyz",
      "restaurantId": "rest-456",
      "restaurantName": "HaBurger",
      "restaurantAddress": { "lat": 32.0853, "lng": 34.7818, "street": "Rothschild Blvd 1" },
      "customerAddress": { "lat": 32.0742, "lng": 34.7922 },
      "estimatedPickupMinutes": 7,
      "estimatedDeliveryMinutes": 22,
      "estimatedEarnings": 18.50,
      "currency": "ILS",
      "items": [{ "name": "Shakshuka", "quantity": 2 }]
    }
  ]
}
```

---

#### `POST /api/v1/deliveries/{orderId}/accept`

First-writer wins via conditional DynamoDB write. Returns `409` if another courier already accepted.

**Request body** — see [`events/accept-delivery.json`](events/accept-delivery.json)

**Response 200**
```json
{
  "orderId": "order-xyz",
  "status": "ASSIGNED",
  "restaurantAddress": { "lat": 32.0853, "lng": 34.7818, "street": "Rothschild Blvd 1" }
}
```

**Response 409**
```json
{ "error": "CONFLICT", "message": "Another courier accepted this order first" }
```

---

#### `POST /api/v1/deliveries/{orderId}/stage`

Courier advances delivery stage.

**Request body** — see [`events/update-delivery-stage.json`](events/update-delivery-stage.json)

`newStage` enum: `PICKED_UP` · `DELIVERED` · `FAILED`  
`failureReason` — required when `newStage = FAILED`: `CUSTOMER_UNREACHABLE` · `WRONG_ADDRESS` · `ACCESS_DENIED` · `CUSTOMER_REFUSED` · `OTHER`

**Response 200**
```json
{ "orderId": "order-xyz", "stage": "PICKED_UP", "updatedAt": "2026-06-28T19:07:00.000Z" }
```

---

#### `POST /api/v1/deliveries/{orderId}/confirm-delivery`

Customer confirms delivery. Transitions to `DELIVERED` once both courier and customer confirm.

**Request body**
```json
{ "customerId": "user-123" }
```

**Response 200**
```json
{ "orderId": "order-xyz", "stage": "DELIVERED", "updatedAt": "2026-06-28T19:28:00.000Z" }
```

---

#### `GET /api/v1/deliveries/{orderId}`

Returns current delivery state. Reads DynamoDB `delivery_assignments` (this service's own table — not Order
Service's `active_orders`) + `courier_states`.

**Response 200**
```json
{
  "orderId": "order-xyz",
  "status": "PICKED_UP",
  "courierId": "courier-001",
  "courierName": "Avi Cohen",
  "courierPhone": "+972501234567",
  "courierLastLocation": { "lat": 32.0800, "lng": 34.7850, "updatedAt": "2026-06-28T19:15:00.000Z" },
  "restaurantName": "HaBurger",
  "restaurantAddress": { "lat": 32.0853, "lng": 34.7818, "street": "Rothschild Blvd 1" },
  "customerAddress": { "lat": 32.0742, "lng": 34.7922 },
  "estimatedDeliveryTime": "2026-06-28T19:30:00.000Z",
  "assignedAt": "2026-06-28T18:51:00.000Z",
  "pickedUpAt": "2026-06-28T19:07:00.000Z",
  "deliveredAt": null
}
```

**Response 404**
```json
{ "error": "NOT_FOUND", "message": "No delivery assignment found for order order-xyz" }
```

---

#### `GET /health`

Fargate / ALB health check.

**Response 200**
```json
{
  "status": "ok",
  "modules": {
    "sqsConsumer": "ready",
    "assignmentEngine": "ready",
    "gpsSyncScheduler": "ready",
    "wazeClient": "ready"
  },
  "timestamp": "2026-06-28T19:00:00.000Z"
}
```

---

### SQS Inbound — `delivery-events`

Messages consumed from the `delivery-events` SQS Standard queue (fan-out from SNS Standard topic `order-events`). The background SQS consumer polls every 5 seconds. DLQ triggers after 3 consecutive processing failures. Duplicates are handled by checking current order state before acting.

See [`events/order-preparing.json`](events/order-preparing.json), [`events/order-cancelled.json`](events/order-cancelled.json), [`events/order-status-ready.json`](events/order-status-ready.json) for payload examples.

Events can also be sent directly to `POST /internal/events` for local testing without SQS.

---

### SNS Outbound — `order-events`

All events published to SNS Standard topic `order-events`.  
Consumers: Notification Service · Monitoring Service · Order Service.

| Event type | Trigger |
|---|---|
| `delivery.courier_assigned` | Assignment engine selects a courier |
| `delivery.status.picked_up` | Courier taps Picked up (`ASSIGNED → PICKED_UP`) |
| `delivery.status.delivered` | Both parties confirm (`PICKED_UP → DELIVERED`) |
| `delivery.status.failed` | Courier reports failure (`PICKED_UP → FAILED`) |
| `delivery.courier_reassigned` | Original courier cancelled mid-delivery |

See [`src/modules/events/model/delivery_event.py`](src/modules/events/model/delivery_event.py) for full schemas.

---

### REST Outbound

The only real outbound call this service makes is to Waze — see below. `GET /couriers/{courierId}/profile`
is not an outbound call: it's an endpoint this service exposes itself (see REST Inbound), backed by a
direct best-effort Supabase query, called from the accept handler before publishing
`delivery.courier_assigned`. `PATCH /orders/{orderId}/status` was never implemented — this service notifies
Order Service only via the SNS events above, never a REST callback (see `docs/ARCHITECTURE.md` §0.6).

#### Waze API — ETA Calls

Up to 20 parallel calls per `order.preparing` event (one per candidate courier). API key stored in AWS Secrets Manager. Falls back to PostGIS distance-only ranking if Waze is unavailable.

---

### DynamoDB Write Shapes

#### Table: `courier_states`

PK: `courierId` (S). Single item per courier — upserted on GPS updates, availability changes, assignment, and order completion.

```json
{
  "courierId": "courier-001",
  "status": "busy",
  "currentOrderId": "order-xyz",
  "vehicleType": "bike",
  "lastLocation": { "lat": 32.08, "lng": 34.785, "updatedAt": "2026-06-28T19:15:00.000Z" },
  "updatedAt": "2026-06-28T19:15:00.000Z"
}
```

`status` enum: `offline` · `available` · `busy`

#### Table: `order_events`

PK: `order_id` (S) · SK: `event_time` (S). Immutable append-only audit log.

```json
{
  "order_id": "order-xyz",
  "event_time": "2026-06-28T19:28:00.000Z",
  "event_type": "delivery.status.delivered",
  "stage": "DELIVERED",
  "previous_stage": "PICKED_UP",
  "actor_id": "courier-001",
  "actor_type": "COURIER",
  "courier_id": "courier-001",
  "metadata": { "courier_confirmed": true, "customer_confirmed": true, "confirmed_by": "COURIER" },
  "event_id": "evt_01J0DS4444ABCD"
}
```

---

### CloudWatch Custom Metrics

Namespace: `FoodDelivery/DeliveryService`.

| Metric | Unit | Alert Threshold |
|--------|------|-----------------|
| `CourierAssignmentLagSeconds` | Seconds | > 120 s |
| `UnacceptedOrdersCount` | Count | > 5 for > 5 min |
| `StageMachineErrorCount` | Count | > 5 errors / 5 min |
| `GpsSyncJobFailureCount` | Count | > 0 (any failure) |
| `WazeApiErrorRate` | Percent | > 10% per 5 min |
| `EligibleCouriersFound` | Count | < 1 for > 3 orders |

---

## Data Stores

| Store | Table | Purpose |
|-------|-------|---------|
| DynamoDB | `courier_states` | Live GPS (every 10 s); courier status (available / busy / offline) |
| DynamoDB | `delivery_assignments` | This service's own assignment/eligibility state (`eligible_courier_ids`, `assigned_courier_id`, stage) — not Order Service's `active_orders` |
| DynamoDB | `order_events` | Immutable stage-transition audit log |
| Supabase PostgreSQL | `courier_locations` | PostGIS geometry; batch-updated from DynamoDB every 10 min |

---

## Docker and deployment

The service image is built from `python:3.12-slim` and runs `uvicorn src.main:app --host 0.0.0.0 --port 8000`
as a non-root user. The container listens on port `8000`, and the health check endpoint is `GET /health`.

GitHub Actions publishes images to Amazon ECR repository:

```text
delivery-service
```

Each push to `main` publishes an immutable tag equal to the full Git commit SHA and also updates `latest`:

```text
<account-id>.dkr.ecr.<region>.amazonaws.com/delivery-service:<github.sha>
<account-id>.dkr.ecr.<region>.amazonaws.com/delivery-service:latest
```

The workflow uses OIDC and requires these GitHub Actions secrets:

```text
AWS_ROLE_ARN
AWS_REGION
```

ECR is assumed to already exist. ECS runtime resources, including the ECS service, task definition, load
balancer wiring, target group, security groups, and runtime CloudFormation stacks, are created from the
`food-delivery-infrastructure` repository, not from this repository.

---

## Scaling & Resilience

**Auto-scaling:** ECS service scales on CPU. 1 task handles steady load; scale-out at 70% CPU for 2 consecutive minutes (up to 4 tasks for lunch-peak GPS volume).

**DLQ:** `delivery-events` SQS queue has a Dead Letter Queue. Messages failing 3 times move to DLQ and trigger a CloudWatch alarm without blocking the queue.

**Race condition (courier accept):** Uses DynamoDB `ConditionExpression: attribute_not_exists(assignedCourierId)`. Only the first writer succeeds; all others receive 409.

**Waze API failure:** Falls back to distance-only eligibility (top-5 nearest from PostGIS) and logs `WazeApiErrorRate`. Ops alerted after > 10% error rate in 5 minutes.

**Duplicate SQS messages:** All event handlers check current order state before acting, making them idempotent.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AWS_REGION` | — | AWS region; GitHub Actions reads it from `secrets.AWS_REGION` |
| `DYNAMODB_TABLE_DELIVERY_ASSIGNMENTS` | `delivery_assignments` | DynamoDB table name |
| `DYNAMODB_TABLE_COURIER_STATES` | `courier_states` | DynamoDB table name |
| `DYNAMODB_TABLE_ORDER_EVENTS` | `order_events` | DynamoDB table name |
| `SNS_TOPIC_ARN_ORDER_EVENTS` | — | SNS topic for outbound delivery events |
| `SQS_QUEUE_URL_DELIVERY_EVENTS` | — | SQS queue URL for inbound order events |
| `SUPABASE_URL` | — | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | — | Supabase service role key |
| `ORDER_SERVICE_URL` | — | Base URL of the Order Service |
| `WAZE_API_KEY` | — | Waze Routing API key (from Secrets Manager) |
| `MAX_COURIER_DISTANCE_MINUTES` | `15` | Max Waze travel time for courier eligibility |
| `GPS_SYNC_INTERVAL_SECONDS` | `600` | How often DynamoDB → Supabase GPS sync runs |
| `SQS_POLL_INTERVAL_SECONDS` | `5` | How often SQS consumer polls for new messages |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `ENVIRONMENT` | `dev` | `dev` / `staging` / `production` |
