"""
Tests for the fixture repository.

Every assertion here is about the bundled sample data. Replace this module
when you replace the repository; see PORTING.md section 7.
"""

import asyncio
from datetime import date, datetime
from typing import Any
from uuid import UUID

import pytest
from common_grants_sdk.schemas.pydantic import (
    OppDefaultFilters,
    OppSortBy,
    PaginatedBodyParams,
    SingleDateEvent,
)

from common_grants.services.fixtures import fixture_repository, opportunities
from common_grants.services.repository import SortSpec

CLEAN_WATER = "0f8d3c1a-4b2e-4c6f-9a10-000000000001"
BROADBAND = "1a9e4d2b-5c3f-4d70-8b21-000000000002"
ARTS = "2b0f5e3c-6d40-4e81-9c32-000000000003"
STEM = "3c1a6f4d-7e51-4f92-8d43-000000000004"
WILDFIRE = "4d2b7a5e-8f62-4a03-9e54-000000000005"
HISTORIC = "5e3c8b6f-9073-4b14-8f65-000000000006"
VOUCHERS = "6f4d9c70-a184-4c25-9076-000000000007"
COASTAL = "7a5e0d81-b295-4d36-8187-000000000008"

ALL_PAGES = PaginatedBodyParams(page=1, pageSize=100)
NEWEST_FIRST_ORDER = SortSpec(OppSortBy.LAST_MODIFIED_AT, "desc")

# Descending lastModifiedAt; the broadband/STEM tie breaks on ascending id.
NEWEST_FIRST = [
    BROADBAND,
    STEM,
    COASTAL,
    CLEAN_WATER,
    WILDFIRE,
    HISTORIC,
    ARTS,
    VOUCHERS,
]


def by_id(opp_id: str):
    return next(o for o in opportunities if str(o.id) == opp_id)


class TestParsing:
    """The bundled data is parsed once, through the shared model."""

    def test_parses_every_record(self):
        assert len(opportunities) == 8
        assert len({o.id for o in opportunities}) == 8

    def test_produces_date_and_datetime_values_rather_than_strings(self):
        clean_water = by_id(CLEAN_WATER)
        assert isinstance(clean_water.last_modified_at, datetime)
        close_date = clean_water.key_dates.close_date if clean_water.key_dates else None
        assert isinstance(close_date, SingleDateEvent)
        assert close_date.date == date(2026, 3, 31)

    def test_keeps_the_date_only_wire_format(self):
        dumped = by_id(CLEAN_WATER).model_dump(mode="json", by_alias=True)
        assert dumped["keyDates"]["closeDate"]["date"] == "2026-03-31"


class TestGet:
    def test_returns_the_record_with_the_requested_id(self):
        found = asyncio.run(fixture_repository.get(UUID(WILDFIRE)))
        assert found is not None
        assert found.title == "Wildfire Resilience Planning"

    def test_returns_none_for_an_id_that_is_not_in_the_data_set(self):
        missing = UUID("00000000-0000-4000-8000-000000000000")
        assert asyncio.run(fixture_repository.get(missing)) is None


class TestList:
    def list_ids(self, page: int, page_size: int) -> tuple[list[str], int]:
        pagination = PaginatedBodyParams(page=page, pageSize=page_size)
        result = asyncio.run(fixture_repository.list(NEWEST_FIRST_ORDER, pagination))
        return [str(o.id) for o in result.items], result.total_items

    def test_applies_the_order_it_is_given(self):
        assert self.list_ids(1, 100) == (NEWEST_FIRST, 8)

    def test_returns_the_first_page_and_the_total_across_all_pages(self):
        assert self.list_ids(1, 3) == (NEWEST_FIRST[:3], 8)

    def test_returns_a_later_partially_filled_page(self):
        assert self.list_ids(3, 3) == (NEWEST_FIRST[6:], 8)

    def test_returns_an_empty_page_past_the_end_without_changing_the_total(self):
        assert self.list_ids(4, 3) == ([], 8)


def search_ids(
    filters: dict[str, Any],
    sorting: SortSpec = NEWEST_FIRST_ORDER,
) -> list[str]:
    applied = OppDefaultFilters.model_validate(filters)
    result = asyncio.run(fixture_repository.search(applied, sorting, ALL_PAGES))
    return [str(o.id) for o in result.items]


def money_range(
    operator: str,
    low: str,
    high: str,
    currency: str = "USD",
) -> dict[str, Any]:
    return {
        "operator": operator,
        "value": {
            "min": {"amount": low, "currency": currency},
            "max": {"amount": high, "currency": currency},
        },
    }


FIRST_HALF_OF_2026 = {"min": "2026-01-01", "max": "2026-06-30"}


class TestSearchFilters:
    def test_matches_a_status_in_filter(self):
        ids = search_ids({"status": {"operator": "in", "value": ["open"]}})
        assert ids == [BROADBAND, COASTAL, CLEAN_WATER, WILDFIRE]

    def test_matches_a_status_not_in_filter(self):
        ids = search_ids({"status": {"operator": "notIn", "value": ["open"]}})
        assert ids == [STEM, HISTORIC, ARTS, VOUCHERS]

    def test_treats_both_ends_of_a_between_date_range_as_inclusive(self):
        ids = search_ids(
            {"closeDateRange": {"operator": "between", "value": FIRST_HALF_OF_2026}},
        )
        assert ids == [BROADBAND, CLEAN_WATER, WILDFIRE]

    def test_excludes_records_with_no_value_for_the_filtered_date_field(self):
        ids = search_ids(
            {"closeDateRange": {"operator": "outside", "value": FIRST_HALF_OF_2026}},
        )
        assert ids == [STEM, COASTAL, ARTS, VOUCHERS]
        assert HISTORIC not in ids

    # The SDK lets either date bound be omitted. A missing bound is unknown, like
    # a missing value, rather than open-ended, so it matches nothing.
    @pytest.mark.parametrize("operator", ["between", "outside"])
    @pytest.mark.parametrize("bounds", [{"min": "2026-01-01"}, {"max": "2026-06-30"}])
    def test_matches_nothing_for_a_missing_date_bound(self, operator, bounds):
        assert (
            search_ids({"closeDateRange": {"operator": operator, "value": bounds}})
            == []
        )

    # Taken literally, an inverted between would match nothing and outside everything.
    @pytest.mark.parametrize("operator", ["between", "outside"])
    def test_matches_nothing_for_an_inverted_date_range(self, operator):
        inverted = {"min": "2026-06-30", "max": "2026-01-01"}
        assert (
            search_ids({"closeDateRange": {"operator": operator, "value": inverted}})
            == []
        )

    @pytest.mark.parametrize("operator", ["between", "outside"])
    def test_matches_nothing_for_an_inverted_money_range(self, operator):
        ids = search_ids(
            {"maxAwardAmountRange": money_range(operator, "250000.00", "10000.00")},
        )
        assert ids == []

    def test_compares_money_ranges_numerically_not_lexically(self):
        ids = search_ids(
            {"maxAwardAmountRange": money_range("between", "10000.00", "250000.00")},
        )
        assert ids == [STEM, CLEAN_WATER, WILDFIRE, ARTS, VOUCHERS]

    def test_excludes_money_amounts_denominated_in_a_different_currency(self):
        eur = money_range("between", "10000.00", "250000.00", "EUR")
        assert search_ids({"maxAwardAmountRange": eur}) == []

    def test_matches_a_total_funding_between_range_at_both_edges(self):
        total = money_range("between", "250000.00", "5000000.00")
        ids = search_ids({"totalFundingAvailableRange": total})
        assert ids == [STEM, CLEAN_WATER, WILDFIRE, ARTS, VOUCHERS]

    def test_matches_a_total_funding_outside_range_and_excludes_missing_values(self):
        total = money_range("outside", "250000.00", "5000000.00")
        ids = search_ids({"totalFundingAvailableRange": total})
        assert ids == [BROADBAND]

    def test_matches_a_min_award_between_range(self):
        ids = search_ids(
            {"minAwardAmountRange": money_range("between", "1000.00", "25000.00")},
        )
        assert ids == [STEM, WILDFIRE, ARTS, VOUCHERS]

    def test_matches_a_min_award_outside_range_and_excludes_missing_values(self):
        ids = search_ids(
            {"minAwardAmountRange": money_range("outside", "5000.00", "100000.00")},
        )
        assert ids == [ARTS]

    def test_matches_a_max_award_outside_range_and_excludes_missing_values(self):
        ids = search_ids(
            {"maxAwardAmountRange": money_range("outside", "50000.00", "250000.00")},
        )
        assert ids == [BROADBAND, ARTS]

    # Coastal Habitat Restoration is the one EUR record. Its max award satisfies
    # both ranges numerically, and only the EUR versions see it.
    CROSS_CURRENCY = (
        ("between", "1000000.00", "5000000.00"),
        ("outside", "10000.00", "250000.00"),
    )

    @pytest.mark.parametrize(("operator", "low", "high"), CROSS_CURRENCY)
    def test_keeps_a_record_in_another_currency_out_of_a_usd_range(
        self,
        operator,
        low,
        high,
    ):
        ids = search_ids(
            {"maxAwardAmountRange": money_range(operator, low, high, "USD")},
        )
        assert COASTAL not in ids

    @pytest.mark.parametrize(("operator", "low", "high"), CROSS_CURRENCY)
    def test_matches_the_eur_record_against_a_eur_range(self, operator, low, high):
        ids = search_ids(
            {"maxAwardAmountRange": money_range(operator, low, high, "EUR")},
        )
        assert ids == [COASTAL]

    def test_combines_multiple_filters_with_and(self):
        ids = search_ids(
            {
                "status": {"operator": "in", "value": ["open"]},
                "closeDateRange": {"operator": "between", "value": FIRST_HALF_OF_2026},
            },
        )
        assert ids == [BROADBAND, CLEAN_WATER, WILDFIRE]

    def test_returns_every_record_when_no_filter_is_supplied(self):
        assert search_ids({}) == NEWEST_FIRST

    def test_paginates_filtered_results_and_reports_the_filtered_total(self):
        applied = OppDefaultFilters.model_validate(
            {"status": {"operator": "in", "value": ["open"]}},
        )
        second_page = PaginatedBodyParams(page=2, pageSize=3)
        result = asyncio.run(
            fixture_repository.search(applied, NEWEST_FIRST_ORDER, second_page),
        )
        assert [str(o.id) for o in result.items] == [WILDFIRE]
        assert result.total_items == 4


SORT_CASES = [
    (
        OppSortBy.LAST_MODIFIED_AT,
        [VOUCHERS, ARTS, HISTORIC, WILDFIRE, CLEAN_WATER, COASTAL, BROADBAND, STEM],
        NEWEST_FIRST,
    ),
    (
        OppSortBy.CREATED_AT,
        [ARTS, VOUCHERS, WILDFIRE, CLEAN_WATER, HISTORIC, STEM, BROADBAND, COASTAL],
        [COASTAL, BROADBAND, STEM, HISTORIC, CLEAN_WATER, WILDFIRE, VOUCHERS, ARTS],
    ),
    (
        OppSortBy.TITLE,
        [CLEAN_WATER, COASTAL, ARTS, HISTORIC, BROADBAND, STEM, VOUCHERS, WILDFIRE],
        [WILDFIRE, VOUCHERS, STEM, BROADBAND, HISTORIC, ARTS, COASTAL, CLEAN_WATER],
    ),
    (
        OppSortBy.STATUS,
        [ARTS, VOUCHERS, HISTORIC, STEM, CLEAN_WATER, BROADBAND, WILDFIRE, COASTAL],
        [CLEAN_WATER, BROADBAND, WILDFIRE, COASTAL, STEM, HISTORIC, ARTS, VOUCHERS],
    ),
    (
        OppSortBy.CLOSE_DATE,
        [ARTS, VOUCHERS, CLEAN_WATER, WILDFIRE, BROADBAND, STEM, COASTAL, HISTORIC],
        [COASTAL, STEM, BROADBAND, CLEAN_WATER, WILDFIRE, VOUCHERS, ARTS, HISTORIC],
    ),
    (
        OppSortBy.MAX_AWARD_AMOUNT,
        [ARTS, VOUCHERS, STEM, WILDFIRE, CLEAN_WATER, BROADBAND, COASTAL, HISTORIC],
        [COASTAL, BROADBAND, CLEAN_WATER, WILDFIRE, STEM, VOUCHERS, ARTS, HISTORIC],
    ),
    (
        OppSortBy.MIN_AWARD_AMOUNT,
        [ARTS, VOUCHERS, WILDFIRE, STEM, CLEAN_WATER, BROADBAND, COASTAL, HISTORIC],
        [COASTAL, BROADBAND, CLEAN_WATER, STEM, WILDFIRE, VOUCHERS, ARTS, HISTORIC],
    ),
    (
        OppSortBy.TOTAL_FUNDING_AVAILABLE,
        [ARTS, WILDFIRE, VOUCHERS, STEM, CLEAN_WATER, BROADBAND, COASTAL, HISTORIC],
        [COASTAL, BROADBAND, CLEAN_WATER, STEM, VOUCHERS, WILDFIRE, ARTS, HISTORIC],
    ),
    (
        OppSortBy.ESTIMATED_AWARD_COUNT,
        [WILDFIRE, COASTAL, BROADBAND, ARTS, CLEAN_WATER, STEM, VOUCHERS, HISTORIC],
        [VOUCHERS, STEM, CLEAN_WATER, ARTS, BROADBAND, COASTAL, WILDFIRE, HISTORIC],
    ),
]


class TestSearchSorting:
    def test_covers_every_protocol_sort_key_except_custom(self):
        assert {case[0] for case in SORT_CASES} == set(OppSortBy) - {OppSortBy.CUSTOM}

    @pytest.mark.parametrize(("sort_by", "ascending", "descending"), SORT_CASES)
    def test_sorts_in_both_directions(self, sort_by, ascending, descending):
        assert search_ids({}, SortSpec(sort_by, "asc")) == ascending
        assert search_ids({}, SortSpec(sort_by, "desc")) == descending
