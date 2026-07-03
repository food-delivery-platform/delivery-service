from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel


def _serialize(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(by_alias=True, mode="json")
    return data


def ok(data: Any) -> JSONResponse:
    return JSONResponse(status_code=200, content=_serialize(data))


def created(data: Any) -> JSONResponse:
    return JSONResponse(status_code=201, content=_serialize(data))


def no_content() -> JSONResponse:
    return JSONResponse(status_code=204, content=None)


def bad_request(code: str, message: str) -> JSONResponse:
    return _error(400, code, message)


def not_found(code: str, message: str) -> JSONResponse:
    return _error(404, code, message)


def conflict(code: str, message: str) -> JSONResponse:
    return _error(409, code, message)


def internal_error(message: str = "Internal server error") -> JSONResponse:
    return _error(500, "INTERNAL_ERROR", message)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": code, "message": message},
    )
