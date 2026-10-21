"""
Test doubles.

The route tests never mention a bundled fixture id or count, so they keep
working after an adopter replaces the fixture repository with their own.
"""

from dataclasses import dataclass, field
from itertools import count
from typing import Any, TypeVar
from uuid import UUID

import pytest
from common_grants_sdk.schemas.pydantic import OppDefaultFilters, PaginatedBase

from common_grants.schemas.opportunity import Opportunity
from common_grants.services.repository import OpportunityRepository, Page, SortSpec

_seq = count(1)
T = TypeVar("T")


def an_opportunity(**overrides: object) -> Opportunity:
    """Build a valid opportunity with a deterministic, overridable shape."""
    n = next(_seq)
    return Opportunity.model_validate(
        {
            "id": f"00000000-0000-4000-8000-{n:012d}",
            "title": f"Opportunity {n}",
            "description": f"Description {n}",
            "status": {"value": "open"},
            "funding": {"maxAwardAmount": {"amount": "1000.00", "currency": "USD"}},
            "keyDates": {
                "closeDate": {
                    "name": "Application deadline",
                    "eventType": "singleDate",
                    "date": "2026-05-01",
                },
            },
            "createdAt": "2026-01-01T00:00:00Z",
            "lastModifiedAt": "2026-01-02T00:00:00Z",
            **overrides,
        },
    )


def a_malformed_opportunity() -> Opportunity:
    """Return an opportunity whose id is not a UUID. `model_copy` skips validation."""
    return an_opportunity().model_copy(update={"id": "not-a-uuid"})


# Dumping a deliberately malformed opportunity makes Pydantic warn before the
# response model rejects it; that warning is expected in these tests.
malformed_data = pytest.mark.filterwarnings(
    "ignore:Pydantic serializer warnings:UserWarning",
)


def page_of(items: list[Opportunity], total_items: int | None = None) -> Page:
    """Wrap items in a page, defaulting the total to the item count."""
    return Page(
        items=items,
        total_items=len(items) if total_items is None else total_items,
    )


@dataclass
class StubRepository:
    """A repository that answers with canned values and records its calls."""

    list_page: Page = field(default_factory=lambda: page_of([]))
    search_page: Page = field(default_factory=lambda: page_of([]))
    found: Opportunity | None = None
    raises: Exception | None = None
    calls: dict[str, list[Any]] = field(
        default_factory=lambda: {"list": [], "get": [], "search": []},
    )

    def _answer(self, value: T) -> T:
        if self.raises is not None:
            raise self.raises
        return value

    async def list(self, sorting: SortSpec, pagination: PaginatedBase) -> Page:
        """Record the call and return the canned list page."""
        self.calls["list"].append({"sorting": sorting, "pagination": pagination})
        return self._answer(self.list_page)

    async def get(self, opp_id: UUID) -> Opportunity | None:
        """Record the call and return the canned opportunity."""
        self.calls["get"].append(opp_id)
        return self._answer(self.found)

    async def search(
        self,
        filters: OppDefaultFilters,
        sorting: SortSpec,
        pagination: PaginatedBase,
    ) -> Page:
        """Record the call and return the canned search page."""
        self.calls["search"].append(
            {"filters": filters, "sorting": sorting, "pagination": pagination},
        )
        return self._answer(self.search_page)


def as_repository(stub: StubRepository) -> OpportunityRepository:
    """Type-check that the stub satisfies the repository protocol."""
    return stub
