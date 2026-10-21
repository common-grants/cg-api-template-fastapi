"""
The data seam.

`create_app()` accepts any `OpportunityRepository`, so connecting a database or
an upstream API means writing one more implementation of this protocol. Nothing
HTTP-shaped crosses it: no envelopes, no status codes, no request objects. The
routes own defaults, pagination metadata and error reporting.
"""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from common_grants_sdk.schemas.pydantic import (
    OppDefaultFilters,
    OppSortBy,
    PaginatedBase,
)

from common_grants.schemas.opportunity import Opportunity


@dataclass(frozen=True)
class SortSpec:
    """A resolved sort. `sort_by` is never `custom`; the routes fall back first."""

    sort_by: OppSortBy
    sort_order: Literal["asc", "desc"]


@dataclass(frozen=True)
class Page:
    """One page of results plus the number of matches across all pages."""

    items: list[Opportunity]
    total_items: int


class OpportunityRepository(Protocol):
    """Where the API reads opportunities from."""

    async def list(self, sorting: SortSpec, pagination: PaginatedBase) -> Page:
        """Every opportunity, in the requested order."""
        ...

    async def get(self, opp_id: UUID) -> Opportunity | None:
        """One opportunity by id, or `None` when no record has that id."""
        ...

    async def search(
        self,
        filters: OppDefaultFilters,
        sorting: SortSpec,
        pagination: PaginatedBase,
    ) -> Page:
        """Opportunities matching every supplied filter, in the requested order."""
        ...
