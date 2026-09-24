"""Tests for the application factory: health, error shaping, no fixture data."""

import pytest
from common_grants_sdk.schemas.pydantic import Error, Success
from fastapi import FastAPI
from fastapi.testclient import TestClient

from common_grants.api import create_app
from tests.support import StubRepository, as_repository


def client(stub: StubRepository | None = None) -> TestClient:
    return TestClient(
        create_app(stub or StubRepository()),
        raise_server_exceptions=False,
    )


def test_create_app_accepts_any_repository():
    """Constructing the app has no side effects and takes the seam as its only input."""
    app = create_app(as_repository(StubRepository()))
    assert isinstance(app, FastAPI)


def test_serves_a_health_check_that_validates_against_the_sdk_success_model():
    response = client().get("/health")
    assert response.status_code == 200
    assert Success.model_validate(response.json()).status == 200


def test_answers_an_unrouted_path_with_a_protocol_shaped_404():
    response = client().get("/no-such-route")
    assert response.status_code == 404
    assert Error.model_validate(response.json()).status == 404


def test_answers_a_disallowed_method_with_a_protocol_shaped_405():
    response = client().delete("/health")
    assert response.status_code == 405
    assert Error.model_validate(response.json()).status == 405
    assert response.headers["allow"] == "GET"


def test_answers_a_malformed_json_body_with_a_protocol_shaped_400():
    response = client().post(
        "/common-grants/opportunities/search",
        content="{ this is not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert Error.model_validate(response.json()).status == 400


def test_answers_a_thrown_repository_failure_with_a_protocol_shaped_500():
    failing = StubRepository(raises=RuntimeError("database is on fire"))

    response = client(failing).get("/common-grants/opportunities")

    assert response.status_code == 500
    assert Error.model_validate(response.json()).status == 500
    # The underlying failure is never returned to the client...
    assert "database is on fire" not in response.text


def test_leaves_a_thrown_repository_failure_for_the_server_to_log():
    # ...but it still propagates, so the server logs the traceback.
    failing = TestClient(
        create_app(StubRepository(raises=RuntimeError("database is on fire"))),
    )
    with pytest.raises(RuntimeError, match="database is on fire"):
        failing.get("/common-grants/opportunities")
