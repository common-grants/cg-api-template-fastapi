"""Tests for the served OpenAPI document and the docs UI."""

from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from common_grants.api import create_app
from common_grants.scripts import generate_openapi
from tests.support import StubRepository

BASE = "/common-grants/opportunities"

OPERATIONS = [
    ("/health", "get", ["200"]),
    (BASE, "get", ["200", "400", "500"]),
    (f"{BASE}/{{oppId}}", "get", ["200", "400", "404", "500"]),
    (f"{BASE}/search", "post", ["200", "400", "500"]),
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(StubRepository()))


@pytest.fixture(scope="module")
def document(client: TestClient) -> dict[str, Any]:
    return client.get("/openapi.json").json()


def resolve(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Follow a local `$ref` to the component it names."""
    while "$ref" in schema:
        schema = document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def json_schema(
    document: dict[str, Any],
    path: str,
    method: str,
    status: str,
) -> dict[str, Any]:
    response = document["paths"][path][method]["responses"][status]
    return resolve(document, response["content"]["application/json"]["schema"])


def test_is_openapi_3_1_with_a_title_and_version(document):
    assert document["openapi"].startswith("3.1")
    assert document["info"]["title"] == "CommonGrants API"
    assert document["info"]["version"] == "0.1.0"


def test_documents_every_route_the_application_registers_and_nothing_else(document):
    documented = sorted(
        f"{method} {path}" for path, ops in document["paths"].items() for method in ops
    )
    assert documented == sorted(f"{method} {path}" for path, method, _ in OPERATIONS)


@pytest.mark.parametrize(("path", "method", "statuses"), OPERATIONS)
def test_gives_each_declared_status_a_json_schema(document, path, method, statuses):
    operation = document["paths"][path][method]
    # FastAPI documents a 422 by default; this API answers validation errors with 400.
    assert sorted(operation["responses"]) == sorted(statuses)
    for status in statuses:
        assert json_schema(document, path, method, status).get("properties")


def test_documents_errors_with_the_sdk_error_model(document):
    error = json_schema(document, BASE, "get", "400")
    assert set(error["required"]) >= {"errors"}
    assert {"status", "message", "errors"} <= set(error["properties"])


def test_drops_fastapis_own_validation_error_schemas(document):
    assert "HTTPValidationError" not in document["components"]["schemas"]
    assert "ValidationError" not in document["components"]["schemas"]


def test_documents_the_list_pagination_parameters(document):
    parameters = document["paths"][BASE]["get"]["parameters"]
    assert {(p["name"], p["in"]) for p in parameters} == {
        ("page", "query"),
        ("pageSize", "query"),
    }


def test_documents_the_protocol_default_page_size_for_the_list_query(document):
    parameters = document["paths"][BASE]["get"]["parameters"]
    [page_size] = [p for p in parameters if p["name"] == "pageSize"]
    assert page_size["schema"]["default"] == 100


def test_documents_the_search_defaults_the_api_applies(document):
    body = document["paths"][f"{BASE}/search"]["post"]["requestBody"]
    schema = body["content"]["application/json"]["schema"]
    options = schema.get("anyOf", [schema])
    request = next(resolve(document, o) for o in options if o.get("type") != "null")

    pagination = resolve(document, request["properties"]["pagination"])
    assert pagination["properties"]["pageSize"]["default"] == 100

    sorting = request["properties"]["sorting"]
    assert sorting["default"]["sortOrder"] == "desc"
    assert resolve(document, sorting)["properties"]["sortOrder"]["default"] == "asc"


def test_documents_the_opportunity_id_as_a_uuid_path_parameter(document):
    [parameter] = document["paths"][f"{BASE}/{{oppId}}"]["get"]["parameters"]
    assert parameter["name"] == "oppId"
    assert parameter["in"] == "path"
    assert parameter["schema"]["format"] == "uuid"


def test_documents_an_optional_search_body_built_from_the_sdk_request_model(document):
    body = document["paths"][f"{BASE}/search"]["post"]["requestBody"]
    assert not body.get("required", False)
    schema = body["content"]["application/json"]["schema"]
    options = schema.get("anyOf", [schema])
    request = next(resolve(document, o) for o in options if o.get("type") != "null")
    assert {"filters", "sorting", "pagination", "search"} <= set(request["properties"])


def test_describes_the_opportunity_payload_rather_than_an_opaque_object(document):
    listing = json_schema(document, BASE, "get", "200")
    item = resolve(document, listing["properties"]["items"]["items"])
    assert {
        "id",
        "title",
        "status",
        "description",
        "createdAt",
        "lastModifiedAt",
    } <= set(
        item["required"],
    )
    assert item["properties"]["id"] == {
        "type": "string",
        "format": "uuid",
        "title": "Id",
        "description": "Globally unique id for the opportunity",
    }
    assert item["properties"]["lastModifiedAt"]["format"] == "date-time"


def test_serves_swagger_ui_pointing_at_the_document(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/openapi.json" in response.text


def test_exports_the_served_document_as_yaml(document, capsys):
    generate_openapi.main()
    assert yaml.safe_load(capsys.readouterr().out) == document


def test_serves_no_second_docs_ui(client):
    # The CommonGrants templates share one docs UI, Swagger UI at /docs.
    assert client.get("/redoc").status_code == 404
