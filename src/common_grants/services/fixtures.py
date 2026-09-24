"""
An in-memory `OpportunityRepository` over the bundled JSON fixtures.

This is the reference implementation of the data seam. It shows what real
filtering, sorting and paging have to handle, using only the protocol's default
filter and sort vocabulary. Replace it with your own repository (see
PORTING.md); the routes never change.

Two behaviors are the template's choice rather than the protocol's, and both
are covered by tests/test_fixtures.py:

- Records with no value for the sort key sort last, in both directions.
- Equal values break the tie on ascending id, in both directions, so a page
  boundary never straddles two records that compare equal.
"""

import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

from common_grants_sdk.schemas.pydantic import (
    ArrayOperator,
    Money,
    MoneyRangeFilter,
    OppDefaultFilters,
    OppSortBy,
    PaginatedBase,
    RangeOperator,
    SingleDateEvent,
)

from common_grants.schemas.opportunity import Opportunity
from common_grants.services.repository import Page, SortSpec

_Bound = TypeVar("_Bound", date, Decimal)

_FIXTURES = Path(__file__).parent.parent / "data" / "opportunities.json"

# Parsed once at import, so a malformed fixture fails on boot, not mid-request.
opportunities: list[Opportunity] = [
    Opportunity.model_validate(record) for record in json.loads(_FIXTURES.read_text())
]


# ############################################################################
# Filtering
# ############################################################################


def _close_date(opportunity: Opportunity) -> date | None:
    event = opportunity.key_dates.close_date if opportunity.key_dates else None
    return event.date if isinstance(event, SingleDateEvent) else None


def _in_range(
    value: _Bound | None,
    operator: RangeOperator,
    low: _Bound | None,
    high: _Bound | None,
) -> bool:
    """
    Whether a value falls in (`between`) or out of (`outside`) an inclusive range.

    A missing value never matches either operator: it is unknown, not outside.
    A missing or inverted bound is unusable in the same way. Taken literally, an
    inverted `between` would match nothing and `outside` every record.
    """
    if value is None or low is None or high is None or low > high:
        return False
    inside = low <= value <= high
    return inside if operator == RangeOperator.BETWEEN else not inside


def _money_matches(money: Money | None, money_filter: MoneyRangeFilter) -> bool:
    """
    Compare amounts as `Decimal`, never as strings or floats.

    A record held in another currency never matches either operator. Without a
    rate the amounts are not comparable, so the record is unknown relative to the
    range rather than outside it. See PORTING.md section 5.
    """
    low, high = money_filter.value.min, money_filter.value.max
    if money is None or not money.currency == low.currency == high.currency:
        return False
    return _in_range(
        Decimal(money.amount),
        money_filter.operator,
        Decimal(low.amount),
        Decimal(high.amount),
    )


def _matches(opportunity: Opportunity, filters: OppDefaultFilters) -> bool:
    if filters.status is not None:
        listed = opportunity.status.value in filters.status.value
        if listed != (filters.status.operator == ArrayOperator.IN):
            return False

    date_filter = filters.close_date_range
    if date_filter is not None and not _in_range(
        _close_date(opportunity),
        date_filter.operator,
        date_filter.value.min,
        date_filter.value.max,
    ):
        return False

    funding = opportunity.funding
    money_filters = [
        (
            filters.total_funding_available_range,
            funding and funding.total_amount_available,
        ),
        (filters.min_award_amount_range, funding and funding.min_award_amount),
        (filters.max_award_amount_range, funding and funding.max_award_amount),
    ]
    return all(
        money_filter is None or _money_matches(money, money_filter)
        for money_filter, money in money_filters
    )


# ############################################################################
# Sorting and paging
# ############################################################################


def _amount(money: Money | None) -> Decimal | None:
    return Decimal(money.amount) if money is not None else None


# Every protocol sort key this repository can execute, and how to read it.
# Money sorts by amount alone; data in several currencies needs a conversion rule.
_SORT_KEYS: dict[OppSortBy, Callable[[Opportunity], Any]] = {
    OppSortBy.LAST_MODIFIED_AT: lambda o: o.last_modified_at,
    OppSortBy.CREATED_AT: lambda o: o.created_at,
    OppSortBy.TITLE: lambda o: o.title,
    # The string value, not the SDK enum's own lifecycle ordering.
    OppSortBy.STATUS: lambda o: str(o.status.value),
    OppSortBy.CLOSE_DATE: _close_date,
    OppSortBy.MAX_AWARD_AMOUNT: lambda o: _amount(
        o.funding and o.funding.max_award_amount,
    ),
    OppSortBy.MIN_AWARD_AMOUNT: lambda o: _amount(
        o.funding and o.funding.min_award_amount,
    ),
    OppSortBy.TOTAL_FUNDING_AVAILABLE: lambda o: _amount(
        o.funding and o.funding.total_amount_available,
    ),
    OppSortBy.ESTIMATED_AWARD_COUNT: lambda o: o.funding
    and o.funding.estimated_award_count,
}


def _sorted(items: list[Opportunity], sorting: SortSpec) -> list[Opportunity]:
    read = _SORT_KEYS[sorting.sort_by]
    # Python's sort is stable, so sorting by id first makes it the tie-break.
    by_id = sorted(items, key=lambda o: str(o.id))
    present = [o for o in by_id if read(o) is not None]
    absent = [o for o in by_id if read(o) is None]
    present.sort(key=read, reverse=sorting.sort_order == "desc")
    return present + absent


def _paginate(items: list[Opportunity], pagination: PaginatedBase) -> Page:
    start = (pagination.page - 1) * pagination.page_size
    return Page(
        items=items[start : start + pagination.page_size],
        total_items=len(items),
    )


class FixtureRepository:
    """Serves the bundled sample data."""

    async def list(self, sorting: SortSpec, pagination: PaginatedBase) -> Page:
        """Return one page of every opportunity, in the requested order."""
        return _paginate(_sorted(opportunities, sorting), pagination)

    async def get(self, opp_id: UUID) -> Opportunity | None:
        """Return the opportunity with this id, or `None`."""
        return next((o for o in opportunities if o.id == opp_id), None)

    async def search(
        self,
        filters: OppDefaultFilters,
        sorting: SortSpec,
        pagination: PaginatedBase,
    ) -> Page:
        """Return one page of the opportunities matching every filter."""
        matched = [o for o in opportunities if _matches(o, filters)]
        return _paginate(_sorted(matched, sorting), pagination)


fixture_repository = FixtureRepository()
