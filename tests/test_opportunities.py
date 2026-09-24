"""
Tests for the opportunity routes.

These drive the routes through a stub repository, so they never mention a
fixture id or count and keep working after you connect your own data.
"""

import math
from typing import Any

import pytest
from common_grants_sdk.schemas.pydantic import (
    Error,
    Filtered,
    OppFilters,
    OppSortBy,
    Paginated,
)
from fastapi.testclient import TestClient

from common_grants.api import create_app
from common_grants.routes.opportunities import OpportunityResponse
from common_grants.schemas.opportunity import Opportunity
from common_grants.services.repository import SortSpec
from tests.support import (
    StubRepository,
    a_malformed_opportunity,
    an_opportunity,
    malformed_data,
    page_of,
)

BASE = "/common-grants/opportunities"

# The list route's order: owned by the routes, handed to the repository.
NEWEST_FIRST = SortSpec(OppSortBy.LAST_MODIFIED_AT, "desc")

# Core's pagination.tsp default; the Python SDK's models say 10.
DEFAULT_PAGE_SIZE = 100

ListResponse = Paginated[Opportunity]
SearchResponse = Filtered[Opportunity, OppFilters]


def harness(**responses: Any) -> tuple[TestClient, StubRepository]:
    stub = StubRepository(**responses)
    return TestClient(create_app(stub), raise_server_exceptions=False), stub


def pages(calls: list[dict[str, Any]]) -> list[tuple[int, int]]:
    return [(call["pagination"].page, call["pagination"].page_size) for call in calls]


class TestListOpportunities:
    def test_returns_a_schema_valid_paginated_envelope(self):
        items = [an_opportunity(), an_opportunity(), an_opportunity()]
        client, _ = harness(list_page=page_of(items, 7))

        response = client.get(BASE)

        assert response.status_code == 200
        body = ListResponse.model_validate(response.json())
        assert body.status == 200
        assert [o.id for o in body.items] == [o.id for o in items]
        assert response.json()["paginationInfo"] == {
            "page": 1,
            "pageSize": DEFAULT_PAGE_SIZE,
            "totalItems": 7,
            "totalPages": math.ceil(7 / DEFAULT_PAGE_SIZE),
        }

    def test_applies_the_protocol_pagination_defaults_and_the_default_order(self):
        client, stub = harness()
        client.get(BASE)
        assert [call["sorting"] for call in stub.calls["list"]] == [NEWEST_FIRST]
        assert pages(stub.calls["list"]) == [(1, DEFAULT_PAGE_SIZE)]

    def test_coerces_numeric_query_strings(self):
        client, stub = harness()
        client.get(f"{BASE}?page=3&pageSize=25")
        assert pages(stub.calls["list"]) == [(3, 25)]

    def test_reports_the_requested_page_size_not_the_page_length(self):
        client, _ = harness(list_page=page_of([an_opportunity()], 21))
        info = client.get(f"{BASE}?pageSize=10").json()["paginationInfo"]
        assert info["pageSize"] == 10
        assert info["totalPages"] == 3

    # Core requires pageSize >= 1 on responses, so an empty page still reports
    # the requested size rather than the item count.
    def test_reports_the_requested_page_size_on_an_empty_page_past_the_end(self):
        client, _ = harness(list_page=page_of([], 21))
        body = client.get(f"{BASE}?page=999&pageSize=10").json()
        assert body["items"] == []
        assert body["paginationInfo"] == {
            "page": 999,
            "pageSize": 10,
            "totalItems": 21,
            "totalPages": 3,
        }

    # The protocol sets a minimum page size and no maximum; the API must not invent one.
    @pytest.mark.parametrize("page_size", [1000, 100000])
    def test_passes_a_large_page_size_through_unchanged(self, page_size):
        client, stub = harness()
        assert client.get(f"{BASE}?pageSize={page_size}").status_code == 200
        assert pages(stub.calls["list"]) == [(1, page_size)]

    @pytest.mark.parametrize(
        "query",
        ["page=abc", "page=0", "pageSize=-1", "pageSize=0", "page=1.5", "pageSize=2.5"],
    )
    def test_rejects_invalid_pagination_with_a_protocol_shaped_400(self, query):
        client, stub = harness()
        response = client.get(f"{BASE}?{query}")

        assert response.status_code == 400
        body = Error.model_validate(response.json())
        assert body.status == 400
        assert body.errors
        assert stub.calls["list"] == []

    @malformed_data
    def test_returns_500_rather_than_a_malformed_200_when_the_repository_lies(
        self,
        caplog,
    ):
        client, _ = harness(list_page=page_of([a_malformed_opportunity()]))
        response = client.get(BASE)
        assert response.status_code == 500
        assert Error.model_validate(response.json()).status == 500
        assert "failed schema validation" in caplog.text


class TestGetOpportunity:
    UNKNOWN = "11111111-2222-4333-8444-555555555555"

    def test_returns_a_schema_valid_200_envelope(self):
        opportunity = an_opportunity()
        client, stub = harness(found=opportunity)

        response = client.get(f"{BASE}/{opportunity.id}")

        assert response.status_code == 200
        body = OpportunityResponse.model_validate(response.json())
        assert body.data.id == opportunity.id
        assert stub.calls["get"] == [opportunity.id]

    def test_returns_a_protocol_shaped_404_for_a_valid_id_with_no_record(self):
        client, _ = harness(found=None)
        response = client.get(f"{BASE}/{self.UNKNOWN}")
        assert response.status_code == 404
        body = Error.model_validate(response.json())
        assert body.status == 404
        assert body.errors == []

    def test_returns_a_protocol_shaped_400_for_an_id_that_is_not_a_uuid(self):
        client, stub = harness()
        response = client.get(f"{BASE}/not-a-uuid")
        assert response.status_code == 400
        assert Error.model_validate(response.json()).status == 400
        assert stub.calls["get"] == []

    @malformed_data
    def test_returns_500_rather_than_a_malformed_200_when_the_repository_lies(self):
        client, _ = harness(found=a_malformed_opportunity())
        response = client.get(f"{BASE}/{self.UNKNOWN}")
        assert response.status_code == 500
        assert Error.model_validate(response.json()).status == 500

    def test_keeps_date_only_and_datetime_wire_formats(self):
        opportunity = an_opportunity()
        client, _ = harness(found=opportunity)
        data = client.get(f"{BASE}/{opportunity.id}").json()["data"]
        assert data["keyDates"]["closeDate"]["date"] == "2026-05-01"
        assert data["lastModifiedAt"] == "2026-01-02T00:00:00Z"


def search(client: TestClient, body: object):
    return client.post(f"{BASE}/search", json=body)


OPEN_ONLY = {"status": {"operator": "in", "value": ["open"]}}


class TestSearchOpportunities:
    def test_returns_a_schema_valid_filtered_envelope(self):
        client, _ = harness(search_page=page_of([an_opportunity(), an_opportunity()]))

        response = search(client, {})

        assert response.status_code == 200
        body = SearchResponse.model_validate(response.json())
        assert len(body.items) == 2
        assert response.json()["sortInfo"] == {
            "sortBy": "lastModifiedAt",
            "sortOrder": "desc",
        }

    def test_accepts_a_request_with_no_body_at_all(self):
        client, stub = harness()
        response = client.post(f"{BASE}/search")

        assert response.status_code == 200
        [call] = stub.calls["search"]
        assert call["filters"].model_dump(exclude_unset=True) == {}
        assert call["sorting"] == NEWEST_FIRST
        assert pages(stub.calls["search"]) == [(1, DEFAULT_PAGE_SIZE)]

    def test_applies_the_protocol_page_size_when_the_body_names_only_a_page(self):
        client, stub = harness()
        search(client, {"pagination": {"page": 2}})
        assert pages(stub.calls["search"]) == [(2, DEFAULT_PAGE_SIZE)]

    def test_passes_the_default_filters_straight_through_to_the_repository(self):
        client, stub = harness()
        search(client, {"filters": OPEN_ONLY})
        [call] = stub.calls["search"]
        assert (
            call["filters"].model_dump(by_alias=True, exclude_unset=True) == OPEN_ONLY
        )

    def test_echoes_only_the_filters_that_were_applied(self):
        client, _ = harness()
        filter_info = search(client, {"filters": OPEN_ONLY}).json()["filterInfo"]
        assert filter_info == {"filters": OPEN_ONLY}

    def test_ignores_unsupported_custom_filters_and_says_so(self):
        client, stub = harness()
        custom = {"customFilters": {"region": {"operator": "eq", "value": "west"}}}

        filter_info = search(client, {"filters": custom}).json()["filterInfo"]

        assert filter_info["errors"] == [
            'Custom filter "region" is not supported by this API and was ignored.',
        ]
        # Not reported as applied, and never passed to the repository.
        assert filter_info["filters"] == {}
        [call] = stub.calls["search"]
        assert call["filters"].model_dump(exclude_unset=True) == {}

    def test_reports_that_free_text_search_was_ignored(self):
        client, _ = harness()
        filter_info = search(client, {"search": "broadband"}).json()["filterInfo"]
        assert filter_info["errors"] == [
            "Free-text search is not implemented by this API and was ignored.",
        ]

    def test_falls_back_to_the_default_order_for_a_custom_sort_key_and_says_so(self):
        client, stub = harness()

        sorting = {"sortBy": "custom", "customSortBy": "relevance"}
        sort_info = search(client, {"sorting": sorting}).json()["sortInfo"]

        assert sort_info["sortBy"] == "lastModifiedAt"
        assert sort_info["sortOrder"] == "desc"
        assert sort_info["customSortBy"] == "relevance"
        assert "relevance" in sort_info["errors"][0]
        assert stub.calls["search"][0]["sorting"] == NEWEST_FIRST

    # The SDK accepts any string for sortOrder; one this API cannot execute is
    # reported rather than silently applied, as ADR-0013 asks for sort keys.
    def test_falls_back_to_the_default_order_for_an_unknown_sort_order_and_says_so(
        self,
    ):
        client, stub = harness()

        sorting = {"sortBy": "title", "sortOrder": "sideways"}
        sort_info = search(client, {"sorting": sorting}).json()["sortInfo"]

        assert sort_info["sortBy"] == "lastModifiedAt"
        assert "sideways" in sort_info["errors"][0]
        assert stub.calls["search"][0]["sorting"] == NEWEST_FIRST

    # Core sets no default direction; ascending matches the other templates.
    def test_defaults_an_explicitly_requested_sort_key_to_ascending(self):
        client, stub = harness()

        sort_info = search(client, {"sorting": {"sortBy": "title"}}).json()["sortInfo"]

        assert sort_info == {"sortBy": "title", "sortOrder": "asc"}
        assert stub.calls["search"][0]["sorting"] == SortSpec(OppSortBy.TITLE, "asc")

    def test_passes_an_explicit_sort_through(self):
        client, stub = harness()
        sorting = {"sortBy": "funding.maxAwardAmount", "sortOrder": "desc"}
        assert search(client, {"sorting": sorting}).json()["sortInfo"] == sorting
        assert stub.calls["search"][0]["sorting"] == SortSpec(
            OppSortBy.MAX_AWARD_AMOUNT,
            "desc",
        )

    # Zero matches means zero pages; the protocol puts no minimum on totalPages.
    def test_reports_zero_pages_when_nothing_matches(self):
        client, _ = harness()
        body = search(client, {}).json()
        assert body["items"] == []
        assert body["paginationInfo"] == {
            "page": 1,
            "pageSize": DEFAULT_PAGE_SIZE,
            "totalItems": 0,
            "totalPages": 0,
        }

    def test_honours_body_pagination(self):
        client, stub = harness()
        search(client, {"pagination": {"page": 4, "pageSize": 5}})
        assert pages(stub.calls["search"]) == [(4, 5)]

    @pytest.mark.parametrize(
        "body",
        [
            {"filters": {"status": {"operator": "nope", "value": ["open"]}}},
            {"filters": {"status": {"operator": "in", "value": "open"}}},
            {"sorting": {"sortBy": "nope"}},
            {"sorting": {"sortBy": "custom"}},
            {"pagination": {"page": 0}},
            {"pagination": {"page": "two"}},
        ],
    )
    def test_rejects_an_invalid_body_with_a_protocol_shaped_400(self, body):
        client, stub = harness()
        response = search(client, body)
        assert response.status_code == 400
        assert Error.model_validate(response.json()).status == 400
        assert stub.calls["search"] == []

    @malformed_data
    def test_returns_500_rather_than_a_malformed_200_when_the_repository_lies(self):
        client, _ = harness(search_page=page_of([a_malformed_opportunity()]))
        response = search(client, {})
        assert response.status_code == 500
        assert Error.model_validate(response.json()).status == 500
