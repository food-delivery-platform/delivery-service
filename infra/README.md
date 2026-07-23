# Delivery Service Runtime Stack

This stack creates only the delivery-service ECS Fargate task definition and
service. It attaches to infrastructure created elsewhere instead of owning
it:

- ECR repository: created manually, not by this stack (`delivery-service`).
- ECS cluster, internal ALB, target group, and task security group: created
  by the `food-delivery-preview-platform` stack in the
  `food-delivery-infrastructure` repository.

This stack itself creates only:

- ECS Fargate task definition
- ECS service (attached to the existing cluster/target group/security group)
- CloudWatch log group
- ECS task execution role and task role (scoped to this service's own
  DynamoDB tables, and to the order-events SNS topic / delivery-events SQS
  queue once those ARNs are supplied)

Stack name must be exactly `delivery-service-runtime`. The shared cleanup
automation in `food-delivery-infrastructure` only knows how to delete that
exact name, `restaurant-service-runtime`, and `food-delivery-preview-platform`.

## Lifecycle

The `food-delivery-preview-platform` stack (and this stack's cluster/ALB/
target group dependencies) only exist for a limited time — someone runs the
`food-delivery-infrastructure` repo's "Deploy delivery and restaurant
preview" workflow with a `lifetime_minutes` input (default 60), and an
EventBridge Scheduler one-time rule deletes everything after that.

This repo's deploy workflow does not create or extend that lifetime. It only
checks whether `food-delivery-preview-platform` currently exists and is
healthy:

- If it is running: build and push the image to ECR, then deploy/update
  `delivery-service-runtime` with the new `ImageUri`, which forces a new ECS
  task-definition revision and a rolling service update.
- If it is not running (already cleaned up, or never deployed): the image is
  still pushed to ECR, but the CloudFormation deploy step is skipped — there
  is no cluster, target group, or security group to attach to.

Also remember: the platform stack's API Gateway route for this service
defaults to `/api/deliveries`, but this service's actual FastAPI prefix is
`/api/v1`. Whoever runs `food-delivery-infrastructure`'s deploy workflow must
override `delivery_base_path=/api/v1`, or every request will 404. That
override lives in the infrastructure repo's workflow input, not in this repo.

## Prerequisites

- `AWS_ROLE_ARN` GitHub secret: OIDC-assumed role with permission to push to
  the `delivery-service` ECR repository, read `food-delivery-preview-platform`
  stack outputs, and deploy/update the `delivery-service-runtime` stack
  (including `iam:PassRole` for the task execution and task roles it
  creates).
- `AWS_REGION` GitHub secret: plain region string (for example `us-east-1`).
- App-config GitHub secrets/variables passed as CloudFormation
  parameter-overrides on every deploy (see `docs/PHASE-9-PLAN.md` for the
  full variable → secret mapping):
  - `SNS_TOPIC_ARN_ORDER_EVENTS`, `SQS_QUEUE_URL_DELIVERY_EVENTS`,
    `SQS_QUEUE_ARN_DELIVERY_EVENTS` (URL is used by the app; the ARN is used
    only to scope the task role's IAM policy)
  - `SUPABASE_URL`, `ORDER_SERVICE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`, `WAZE_API_KEY` — **OPEN GAP**: neither is
    provisioned yet in this repo's GitHub Actions Secrets or in AWS Secrets
    Manager. Until resolved, deploys run in a documented degraded mode
    (Supabase calls fail, Waze falls back to distance-only ETA/eligibility).

None of these secrets need to exist for `Dockerfile`, `infra/cloudformation.yml`,
or the deploy workflow itself to be valid — they're only read at the moment
a real deploy runs.
