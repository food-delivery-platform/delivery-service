from fastapi import Header, Query


def get_current_courier_id(
    authorization: str | None = Header(default=None),
    courier_id: str | None = Query(default=None, alias="courierId"),
) -> str | None:
    """Stub JWT extraction — Cognito auth isn't wired up yet (docs/PLAN.md Phase 2).

    Real Cognito JWTs will arrive as `Authorization: Bearer <jwt>`; this is a one-line swap once
    a JWT verifier exists. `courierId` query param is a local-dev/curl convenience in the meantime.
    """
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ")
    return courier_id
