# delivery-service

Handles the full delivery lifecycle for the Food Delivery Platform: GPS collection, courier proximity assignment, delivery stage transitions, and ETA calculations.

**Runtime:** Node.js + Express · AWS Fargate (1–4 tasks, auto-scales at 70% CPU)  
**Owned data:** DynamoDB `courier_states`, `active_orders`, `order_events` · Supabase `courier_locations`, `assignments`

---

## Table of Contents

- [Overview](#overview)
- [Why Fargate](#why-fargate)
- [Internal Modules](#internal-modules)
- [External DTOs](#external-dtos)
  - [SQS Inbound — `delivery-events`](#sqs-inbound--delivery-events)
  - [SNS Outbound — `order-events`](#sns-outbound--order-events)
  - [REST Inbound](#rest-inbound)
  - [REST Outbound](#rest-outbound)
  - [DynamoDB Write Shapes](#dynamodb-write-shapes)
  - [CloudWatch Custom Metrics](#cloudwatch-custom-metrics)
- [Data Stores](#data-stores)
- [Scaling & Resilience](#scaling--resilience)

---

## Overview

The Delivery Service sits between the Order Service and couriers. It receives `order.preparing` events from SQS, finds the best available couriers via PostGIS + Waze, broadcasts available orders for couriers to poll, and tracks every stage until delivery is confirmed by both courier and customer.

```
Order Service (SQS) → [Assignment Engine] → DynamoDB eligible_courier_ids
                                                    ↓
                              Courier App polls GET /deliveries/available (30 s)
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

1. **In-process GPS sync scheduler** — a background job runs every 10 minutes to batch-sync courier GPS from DynamoDB to Supabase `courier_locations` for PostGIS spatial queries. Lambda's request-scoped model cannot host a recurring in-process job.
2. **Waze API call chains** — assigning a courier requires calling Waze once per candidate (up to 20 calls per `order.preparing` event). A warm Express server avoids Lambda cold-start latency on this critical path.
3. **Persistent PostgreSQL connection pool** — PostGIS nearest-courier queries benefit from a warm `pg-pool`; reconnecting on every invocation adds measurable latency.

---

## Internal Modules

| Module | Trigger | Responsibility |
|--------|---------|----------------|
| **GPS handler** | `PATCH /couriers/{id}/gps` every 10 s | Writes courier position to DynamoDB `courier_states.lastLocation` |
| **GPS sync scheduler** | In-process `setInterval`, every 10 min | Reads all active courier GPS from DynamoDB; batch-upserts PostGIS geometry to Supabase `courier_locations` |
| **ETA handler** | `GET /deliveries/eta` | Calls Waze for restaurant→customer travel time; returned to Order Service before checkout |
| **SQS consumer** | SQS Standard `delivery-events` | Routes `order.preparing` → Assignment Engine; `order.cancelled` → release courier; `order.status.ready` → update broadcast status |
| **Assignment engine** | `order.preparing` event | (1) PostGIS: 20 nearest couriers to restaurant, (2) Waze per courier for arrival time, (3) keep those ≤ threshold, (4) write `eligible_courier_ids` to DynamoDB |
| **Poll handler** | `GET /deliveries/available` every 30 s | Returns paid orders for which this courier appears in `eligible_courier_ids` |
| **Accept handler** | `POST /deliveries/{id}/accept` | Conditional DynamoDB write (`attribute_not_exists(assignedCourierId)`); 409 if another courier already accepted |
| **Stage state machine** | Courier `POST /stage`; Customer `POST /confirm-delivery` | `ASSIGNED → PICKED_UP → DELIVERED / FAILED`; writes `order_events` audit log; publishes to SNS; calls Order Service status patch |
| **Health check** | `GET /health` | ALB target group readiness probe |

---

## External DTOs

### SQS Inbound — `delivery-events`

Messages consumed from the `delivery-events` SQS Standard queue (fan-out from SNS Standard topic `order-events`). DLQ triggers after **3 consecutive processing failures**. Duplicates are handled by checking current order state before acting.

---

#### `order.preparing`

Published by Order Service (Step Functions) on payment confirmation. Triggers the Assignment Engine.

```json
{
  "eventType": "order.preparing",
  "eventId": "evt_01J0XYZ1234ABCD",
  "timestamp": "2026-06-28T18:50:00.000Z",
  "orderId": "order-xyz",
  "customerId": "user-123",
  "restaurantId": "rest-456",
  "restaurantAddress": {
    "lat": 32.0853,
    "lng": 34.7818,
    "street": "Rothschild Blvd 1",
    "city": "Tel Aviv"
  },
  "deliveryAddress": {
    "addressId": "addr-789",
    "lat": 32.0742,
    "lng": 34.7922,
    "street": "Ben Yehuda St 44",
    "city": "Tel Aviv"
  },
  "estimatedPickupTime": "2026-06-28T19:05:00.000Z",
  "estimatedDeliveryTime": "2026-06-28T19:30:00.000Z",
  "items": [
    { "menuItemId": "item-1", "name": "Shakshuka", "quantity": 2, "timeToPrepare": 15 }
  ],
  "totalAmount": 78.50,
  "currency": "ILS",
  "actorId": "SYSTEM"
}
```

---

#### `order.cancelled`

Published by Order Service on payment failure or invalid order. The service releases any pre-assigned courier.

```json
{
  "eventType": "order.cancelled",
  "eventId": "evt_01J0XYZ9999ABCD",
  "timestamp": "2026-06-28T18:55:00.000Z",
  "orderId": "order-xyz",
  "reason": "PAYMENT_FAILED",
  "actorId": "SYSTEM"
}
```

`reason` enum: `PAYMENT_FAILED` · `INVALID_ORDER` · `CUSTOMER_CANCELLED`

---

#### `order.status.ready`

Published by Order Service when the kitchen marks the order ready. Updates the broadcast status so the assigned courier knows food is ready for pickup.

```json
{
  "eventType": "order.status.ready",
  "eventId": "evt_01J0XYZ5678ABCD",
  "timestamp": "2026-06-28T19:05:00.000Z",
  "orderId": "order-xyz",
  "restaurantId": "rest-456",
  "courierId": "courier-001",
  "actorId": "rest-456"
}
```

---

### SNS Outbound — `order-events`

All events published to SNS Standard topic `order-events`.  
`SNSTopicArn`: `arn:aws:sns:eu-west-1:123456789012:order-events`  
Consumers: Notification Service · Monitoring Service · Order Service.

---

#### `delivery.courier_assigned`

Emitted after the Assignment Engine selects a courier (first-accept-wins).

```json
{
  "eventType": "delivery.courier_assigned",
  "eventId": "evt_01J0DS1234ABCD",
  "timestamp": "2026-06-28T18:51:00.000Z",
  "orderId": "order-xyz",
  "courierId": "courier-001",
  "courierName": "Avi Cohen",
  "courierPhone": "+972501234567",
  "vehicleType": "bike",
  "estimatedPickupTime": "2026-06-28T19:05:00.000Z",
  "estimatedDeliveryTime": "2026-06-28T19:30:00.000Z",
  "actorId": "SYSTEM"
}
```

`vehicleType` enum: `bike` · `car` · `walk`

---

#### `delivery.status.picked_up`

Courier taps **Picked up**. Stage transition: `ASSIGNED → PICKED_UP`.

```json
{
  "eventType": "delivery.status.picked_up",
  "eventId": "evt_01J0DS2222ABCD",
  "timestamp": "2026-06-28T19:07:00.000Z",
  "orderId": "order-xyz",
  "courierId": "courier-001",
  "actorId": "courier-001"
}
```

---

#### `delivery.status.delivered`

Both courier and customer confirm delivery. Stage transition: `PICKED_UP → DELIVERED`. Terminal event.

```json
{
  "eventType": "delivery.status.delivered",
  "eventId": "evt_01J0DS4444ABCD",
  "timestamp": "2026-06-28T19:28:00.000Z",
  "orderId": "order-xyz",
  "courierId": "courier-001",
  "courierConfirmed": true,
  "customerConfirmed": true,
  "confirmedBy": "COURIER",
  "actualDeliveryTime": "2026-06-28T19:28:00.000Z",
  "actorId": "courier-001"
}
```

`confirmedBy`: `COURIER` · `CUSTOMER` — records which party triggered the final status push.

---

#### `delivery.status.failed`

Courier reports failure. Stage transition: `PICKED_UP → FAILED`.

```json
{
  "eventType": "delivery.status.failed",
  "eventId": "evt_01J0DS5555ABCD",
  "timestamp": "2026-06-28T19:35:00.000Z",
  "orderId": "order-xyz",
  "courierId": "courier-001",
  "failureReason": "CUSTOMER_UNREACHABLE",
  "failureNote": "Rang doorbell 3 times, no answer. Tried calling.",
  "actorId": "courier-001"
}
```

`failureReason` enum: `CUSTOMER_UNREACHABLE` · `WRONG_ADDRESS` · `ACCESS_DENIED` · `CUSTOMER_REFUSED` · `OTHER`

---

#### `delivery.courier_reassigned`

Emitted when the original courier cancels or becomes unresponsive mid-delivery.

```json
{
  "eventType": "delivery.courier_reassigned",
  "eventId": "evt_01J0DS6666ABCD",
  "timestamp": "2026-06-28T19:10:00.000Z",
  "orderId": "order-xyz",
  "previousCourierId": "courier-001",
  "newCourierId": "courier-007",
  "reason": "COURIER_CANCELLED",
  "actorId": "SYSTEM"
}
```

`reason` enum: `COURIER_CANCELLED` · `COURIER_UNRESPONSIVE` · `MANUAL_OPS`

---

### REST Inbound

Exposed via ALB (Fargate target group). Courier App endpoints require `Authorization: Bearer <cognito_jwt>`. Customer App endpoints require a Firebase session cookie verified server-side.

---

#### `PATCH /api/v1/couriers/{courierId}/gps`

Courier App sends GPS position every 10 seconds. Writes to DynamoDB `courier_states.lastLocation` (live source of truth). Supabase `courier_locations` is batch-synced from DynamoDB every 10 minutes.

**Request**
```json
{
  "lat": 32.0800,
  "lng": 34.7850,
  "timestamp": "2026-06-28T19:15:00.000Z"
}
```

**Response 200** — empty body.

---

#### `GET /api/v1/deliveries/eta`

Called by Order Service at checkout. Returns Waze-calculated restaurant→customer travel time so the customer sees an accurate ETA before paying.

**Request**
```
GET /api/v1/deliveries/eta?restaurantId=rest-456&deliveryLat=32.0742&deliveryLng=34.7922
Authorization: Bearer <internal_service_jwt>
```

**Response 200**
```json
{
  "estimatedDeliveryMinutes": 22,
  "restaurantToCustomerKm": 3.1,
  "calculatedAt": "2026-06-28T18:49:00.000Z"
}
```

If Waze is unavailable, the service returns a distance-based estimate and sets `"source": "fallback_distance"`.

---

#### `GET /api/v1/deliveries/available`

Courier App polls every 30 seconds. Returns paid orders for which this courier is in `eligible_courier_ids`. The courier's ID is extracted from the JWT — no lat/lng parameter needed.

**Request**
```
GET /api/v1/deliveries/available
Authorization: Bearer <jwt_access_token>
```

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

Courier accepts an available order. First-writer wins via conditional DynamoDB write. Returns `409 Conflict` if another courier already accepted.

**Request**
```json
{
  "courierId": "courier-001",
  "acceptedAt": "2026-06-28T18:51:45.000Z"
}
```

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
{
  "error": "ALREADY_ASSIGNED",
  "message": "Another courier accepted this order first"
}
```

---

#### `POST /api/v1/deliveries/{orderId}/stage`

Courier advances delivery stage. Triggers the Stage State Machine.

**Request**
```json
{
  "courierId": "courier-001",
  "newStage": "PICKED_UP",
  "failureReason": null
}
```

`newStage` enum: `PICKED_UP` · `DELIVERED` · `FAILED`  
`failureReason` — required when `newStage = FAILED`. Enum: `CUSTOMER_UNREACHABLE` · `WRONG_ADDRESS` · `ACCESS_DENIED` · `CUSTOMER_REFUSED` · `OTHER`

**Response 200**
```json
{
  "orderId": "order-xyz",
  "stage": "PICKED_UP",
  "updatedAt": "2026-06-28T19:07:00.000Z"
}
```

---

#### `POST /api/v1/deliveries/{orderId}/confirm-delivery`

Customer confirms delivery. Delivery transitions to `DELIVERED` once both courier (`newStage: DELIVERED`) and customer have confirmed — no photo required.

**Request**
```json
{
  "customerId": "user-123"
}
```

**Response 200**
```json
{
  "orderId": "order-xyz",
  "stage": "DELIVERED",
  "updatedAt": "2026-06-28T19:28:00.000Z"
}
```

---

#### `GET /api/v1/deliveries/{orderId}`

Returns current delivery state. Reads from DynamoDB `active_orders` (status) and `courier_states` (last GPS).  
**Callers:** Customer App (polls every 5 s) · Ops Dashboard · Order Service.

**Response 200**
```json
{
  "orderId": "order-xyz",
  "status": "PICKED_UP",
  "courierId": "courier-001",
  "courierName": "Avi Cohen",
  "courierPhone": "+972501234567",
  "courierLastLocation": {
    "lat": 32.0800,
    "lng": 34.7850,
    "updatedAt": "2026-06-28T19:15:00.000Z"
  },
  "estimatedDeliveryTime": "2026-06-28T19:30:00.000Z",
  "assignedAt": "2026-06-28T18:51:00.000Z",
  "pickedUpAt": "2026-06-28T19:07:00.000Z",
  "deliveredAt": null
}
```

`status` enum: `ASSIGNED` · `PICKED_UP` · `DELIVERED` · `FAILED`  
`courierLastLocation` reflects the last GPS push (up to 10 s stale).

**Response 404**
```json
{
  "error": "DELIVERY_NOT_FOUND",
  "message": "No delivery assignment found for order order-xyz"
}
```

---

#### `GET /health`

Fargate / ALB health check. Returns `200` when all modules are ready; `503` when any critical module fails — ALB stops routing traffic to this task.

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

**Response 503**
```json
{
  "status": "degraded",
  "modules": {
    "sqsConsumer": "error",
    "assignmentEngine": "ready",
    "gpsSyncScheduler": "ready",
    "wazeClient": "ready"
  },
  "timestamp": "2026-06-28T19:00:00.000Z"
}
```

---

### REST Outbound

Calls made by the Delivery Service to other services and external APIs. Internal calls use a service JWT.

---

#### `GET /api/v1/couriers/{courierId}/profile` → User Service

Called by the Assignment Engine after filtering, to fetch name and phone for the selected courier before emitting `delivery.courier_assigned`.

**Response 200**
```json
{
  "courierId": "courier-001",
  "name": "Avi Cohen",
  "phone": "+972501234567",
  "vehicleType": "bike"
}
```

---

#### Waze API — ETA Calls

Authentication via API key stored in AWS Secrets Manager. Called in two contexts:

**Assignment (courier → restaurant):** up to 20 calls per `order.preparing` event, once per candidate courier. The Assignment Engine keeps couriers where `totalRouteTime / 60 ≤ X_MINUTES_THRESHOLD` (configurable, default 15 min).

```
GET https://waze.com/row-RoutingManager/routingRequest
  ?from=ll.{courierLat}%2C{courierLng}
  &to=ll.{restaurantLat}%2C{restaurantLng}
  &at=0&returnJSON=true
Authorization: <waze_api_key>
```

Response (used fields):
```json
{
  "alternatives": [
    { "response": { "totalRouteTime": 420 } }
  ]
}
```

**Pre-payment ETA (restaurant → customer):** same endpoint with `from` = restaurant coords, `to` = customer delivery address. Returns `estimatedDeliveryMinutes` for `GET /deliveries/eta`.

---

#### `PATCH /api/v1/orders/{orderId}/status` → Order Service

Called by the Stage State Machine on every delivery stage change. On terminal states (`DELIVERED` / `FAILED`), Order Service additionally archives the complete order record to Supabase and deletes the DynamoDB item.

**Request**
```json
{
  "status": "DELIVERED",
  "actorId": "courier-001",
  "timestamp": "2026-06-23T19:28:00.000Z"
}
```

`status` enum: `PICKED_UP` · `DELIVERED` · `FAILED`

**Response 200**
```json
{
  "orderId": "order-xyz",
  "status": "DELIVERED",
  "updatedAt": "2026-06-23T19:28:00.000Z"
}
```

---

### DynamoDB Write Shapes

Attribute type notation: `S` = String · `N` = Number · `M` = Map · `BOOL` = Boolean.

---

#### Table: `courier_states`

PK: `courierId` (S). Single item per courier — upserted on GPS updates, availability changes, assignment, and order completion.

```json
{
  "courierId":      { "S": "courier-001" },
  "status":         { "S": "busy" },
  "currentOrderId": { "S": "order-xyz" },
  "vehicleType":    { "S": "bike" },
  "lastLocation": {
    "M": {
      "lat":       { "N": "32.08" },
      "lng":       { "N": "34.785" },
      "updatedAt": { "S": "2026-06-23T19:15:00.000Z" }
    }
  },
  "updatedAt": { "S": "2026-06-23T19:15:00.000Z" }
}
```

`status` enum: `offline` · `available` · `busy`  
`currentOrderId` — present only when `status = "busy"`; cleared when the order completes.

**Write triggers:**

| Event | `status` | `currentOrderId` |
|-------|----------|-----------------|
| Courier goes available | `available` | — |
| Courier goes offline | `offline` | cleared |
| Courier assigned | `busy` | set to `orderId` |
| GPS push every 10 s | unchanged | unchanged — only `lastLocation` updated |
| Order `DELIVERED` / `FAILED` | `available` | cleared |

**GSIs:**

| GSI | Purpose |
|-----|---------|
| `GSI_couriers_by_status` (PK: `status`, SK: `updatedAt`) | Assignment Engine queries `status = "available"` |
| `GSI_courier_by_current_order` (PK: `currentOrderId`) | Look up which courier is assigned to a given order |

---

#### Table: `order_events`

PK: `order_id` (S) · SK: `event_time` (S). Immutable append-only audit log written on every delivery stage transition.

```json
{
  "order_id":       { "S": "order-xyz" },
  "event_time":     { "S": "2026-06-28T19:28:00.000Z" },
  "event_type":     { "S": "delivery.status.delivered" },
  "stage":          { "S": "DELIVERED" },
  "previous_stage": { "S": "PICKED_UP" },
  "actor_id":       { "S": "courier-001" },
  "actor_type":     { "S": "COURIER" },
  "courier_id":     { "S": "courier-001" },
  "metadata": {
    "M": {
      "courier_confirmed":  { "BOOL": true },
      "customer_confirmed": { "BOOL": true },
      "confirmed_by":       { "S": "COURIER" }
    }
  },
  "event_id": { "S": "evt_01J0DS4444ABCD" }
}
```

`actor_type` enum: `COURIER` · `CUSTOMER` · `SYSTEM`

---

### CloudWatch Custom Metrics

Namespace: `FoodDelivery/DeliveryService`. All alarms fan out to the SNS ops alert topic.

| Metric | Unit | Alarm Threshold |
|--------|------|-----------------|
| `CourierAssignmentLagSeconds` | Seconds | > 120 s |
| `UnacceptedOrdersCount` | Count | > 5 for > 5 min |
| `StageMachineErrorCount` | Count | > 5 errors / 5 min |
| `GpsSyncJobFailureCount` | Count | > 0 (any failure) |
| `WazeApiErrorRate` | Percent | > 10% per 5 min |
| `EligibleCouriersFound` | Count | < 1 for > 3 orders (no coverage alert) |

Example `PutMetricData` shape:
```json
{
  "MetricName": "CourierAssignmentLagSeconds",
  "Namespace": "FoodDelivery/DeliveryService",
  "Unit": "Seconds",
  "Value": 8.4,
  "Dimensions": [
    { "Name": "Environment", "Value": "production" }
  ]
}
```

---

## Data Stores

| Store | Table | Purpose |
|-------|-------|---------|
| DynamoDB | `courier_states` | Live GPS (every 10 s); courier status (available / busy / offline) |
| DynamoDB | `active_orders` | Order state + `eligible_courier_ids` written by Assignment Engine |
| DynamoDB | `order_events` | Immutable stage-transition audit log |
| Supabase PostgreSQL | `courier_locations` | PostGIS geometry; batch-updated from DynamoDB every 10 min |
| Supabase PostgreSQL | `assignments` | Permanent courier-to-order assignment records |

---

## Scaling & Resilience

**Auto-scaling:** ECS service scales on CPU. 1 task handles steady load; scale-out triggers at 70% CPU for 2 consecutive minutes (up to 4 tasks for lunch-peak GPS volume).

**DLQ:** The `delivery-events` SQS queue has a Dead Letter Queue. Messages failing 3 times move to DLQ and trigger a CloudWatch alarm without blocking the queue.

**Race condition (courier accept):** Uses DynamoDB `ConditionExpression: attribute_not_exists(assignedCourierId)`. Only the first writer succeeds; all others receive 409.

**Waze API failure:** Falls back to distance-only eligibility (top-5 nearest from PostGIS) and logs `WazeApiErrorRate`. Ops alerted after > 10% error rate in 5 minutes.

**Duplicate SQS messages:** The service checks current order state before acting on any inbound event, making all handlers idempotent.
