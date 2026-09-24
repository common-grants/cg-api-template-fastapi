"""
The application factory.

`create_app()` builds the whole API from one dependency, an
`OpportunityRepository`, and never opens a socket. The test suite and the
OpenAPI export both build apps this way.
"""

import logging
from collections.abc import Mapping
from typing import Any

from common_grants_sdk.schemas.pydantic import Error, Success
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from common_grants.routes.opportunities import router as opportunities_router
from common_grants.services.fixtures import fixture_repository
from common_grants.services.repository import OpportunityRepository

logger = logging.getLogger(__name__)


def _error(
    status: int,
    message: str,
    errors: list[Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Every non-2xx body validates against the SDK's `Error` model."""
    body = Error(status=status, message=message, errors=errors or [])
    return JSONResponse(
        body.model_dump(mode="json"),
        status_code=status,
        headers=headers,
    )


async def _invalid_request(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Answer 400 in the SDK's `Error` shape, not FastAPI's own 422 body."""
    return _error(400, "Invalid request", jsonable_encoder(exc.errors()))


async def _http_error(_request: Request, exc: HTTPException) -> JSONResponse:
    """Shape unknown routes, disallowed methods, and unknown opportunity ids."""
    return _error(exc.status_code, str(exc.detail), headers=exc.headers)


async def _invalid_response(
    _request: Request,
    exc: ResponseValidationError,
) -> JSONResponse:
    """Answer 500 when the repository returns data that fails the published schema."""
    logger.error("Response failed schema validation: %s", exc.errors())
    return _error(500, "The server could not produce a valid response")


async def _unhandled(_request: Request, _exc: Exception) -> JSONResponse:
    """Answer 500; Starlette re-raises afterwards, so the server logs the traceback."""
    return _error(500, "Internal server error")


async def health() -> dict[str, Any]:
    """Return 200 while the service is able to handle requests."""
    return {"status": 200, "message": "ok"}


def create_app(repository: OpportunityRepository) -> FastAPI:
    """Build the CommonGrants API over any repository implementation."""
    app = FastAPI()
    app.state.repository = repository
    app.add_api_route(
        "/health",
        health,
        methods=["GET"],
        tags=["Operations"],
        summary="Health check",
        response_model=Success,
    )
    app.include_router(opportunities_router)
    app.exception_handler(RequestValidationError)(_invalid_request)
    app.exception_handler(HTTPException)(_http_error)
    app.exception_handler(ResponseValidationError)(_invalid_response)
    app.exception_handler(Exception)(_unhandled)
    return app


# The app `fastapi dev` and `fastapi run` serve. Swap the repository here.
app = create_app(fixture_repository)
