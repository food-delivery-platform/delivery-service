# Initialize Delivery Service as a FastAPI Backend

## Description

Initialize the `delivery-service` repository as a Python FastAPI backend service.

Delivery Service should be implemented as a single FastAPI application, not as a set of AWS Lambda handlers.

The service is responsible for courier assignment, available deliveries, delivery stage updates, courier location updates, delivery tracking, handling inbound order events, and publishing outbound delivery events.

The service should expose REST API endpoints for frontend/internal service calls and provide internal event-processing logic for order-related events.

## Tasks

- Create repository `delivery-service`.
- Initialize Python project.
- Add virtual environment instructions.
- Add dependency management file.
- Add FastAPI application entrypoint.
- Add route modules for delivery, courier, health, and internal event endpoints.
- Add Python domain models and API DTOs.
- Add shared AWS client modules.
- Add shared HTTP response helpers.
- Add shared error handling.
- Add local test event folder.
- Add README placeholder.
- Do not create Flask, Express, Fastify, or AWS Lambda handler structure.

## Required Feature-Based Structure

The project should use this structure:

```text
delivery-service/
  requirements.txt
  README.md

  events/
    order-preparing.json
    order-cancelled.json
    order-status-ready.json
    accept-delivery.json
    update-delivery-stage.json
    update-courier-location.json

  src/
    main.py

    api/
      routes/
        deliveries.py
        couriers.py
        events.py
        health.py

    modules/
      deliveries/
        api/
          dtos.py
        model/
          delivery.py
          delivery_stage.py
          delivery_address.py
        repository/
        service/
        validation/

      couriers/
        api/
          dtos.py
        model/
          courier_state.py
          courier_location.py
          vehicle_type.py
        repository/
        service/

      events/
        model/
          order_event.py
          delivery_event.py
        publisher/
        consumer/

    shared/
      config/
        env.py
      aws/
        dynamodb_client.py
        sns_client.py
        sqs_client.py
      db/
        supabase_client.py
      errors/
        app_error.py
      http/
        api_response.py
      utils/