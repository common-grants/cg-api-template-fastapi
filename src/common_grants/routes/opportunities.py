"""
The `/common-grants/opportunities` routes.

Requests are validated by the SDK's request models and every success body by
its SDK response model, through FastAPI's `response_model`. The routes own
everything the repository deliberately does not: defaults, envelopes,
pagination metadata, and truthful reporting of what was not applied.
"""

import math
from typing import Annotated, Any, Literal
from uuid import UUID

from common_grants_sdk.schemas.pydantic import (
    Error,
    Filtered,
    OppDefaultFilters,
    OppFilters,
    OpportunitySearchRequest,
    OppSortBy,
    OppSorting,
    Paginated,
    PaginatedBase,
    PaginatedQueryParams,
    Success,
)
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request

from common_grants.schemas.opportunity import Opportunity
from common_grants.services.repository import OpportunityRepository, Page, SortSpec


def get_repository(request: Request) -> OpportunityRepository:
    """FastAPI dependency that yields the repository the app was built with."""
    return request.app.state.repository


Repository = Annotated[OpportunityRepository, Depends(get_repository)]

OpportunitiesListResponse = Paginated[Opportunity]
OpportunitiesSearchResponse = Filtered[Opportunity, OppFilters]


class OpportunityResponse(Success):
    """One opportunity. The SDK's own `OpportunityResponse` is fixed to `OpportunityBase`."""

    data: Opportunity


class OpportunityNotFoundError(HTTPException):
    """No opportunity has the requested id; the app shapes it as the SDK's `Error`."""

    def __init__(self) -> None:
        """Answer 404 with the protocol's not-found message."""
        super().__init__(status_code=404, detail="Opportunity not found")


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": Error, "description": "The request did not match the schema"},
    500: {
        "model": Error,
        "description": "The server could not produce a valid response",
    },
}

# The list route's order, and the fallback for a sort this API cannot execute.
DEFAULT_SORT = SortSpec(OppSortBy.LAST_MODIFIED_AT, "desc")

# The SDK types sortOrder as any string; these are the ones this API executes.
SORT_ORDERS: dict[str, Literal["asc", "desc"]] = {"asc": "asc", "desc": "desc"}

router = APIRouter(prefix="/common-grants/opportunities", tags=["Opportunities"])


def _plain(opportunity: Opportunity) -> dict[str, Any]:
    """Plain data, so `response_model` re-validates it; FastAPI trusts model instances."""
    return opportunity.model_dump(by_alias=True, exclude_unset=True)


def _pagination_info(page: Page, pagination: PaginatedBase) -> dict[str, int]:
    """`pageSize` is the requested size, not the number of items on this page."""
    return {
        "page": pagination.page,
        "pageSize": pagination.page_size,
        "totalItems": page.total_items,
        "totalPages": math.ceil(page.total_items / pagination.page_size),
    }


def _resolve_sorting(sorting: OppSorting) -> tuple[SortSpec, dict[str, Any]]:
    """
    Turn a sort request into one the repository can execute, plus a truthful `sortInfo`.

    This API advertises no implementation-defined sort keys, so `custom` falls
    back to the default order and says so in `sortInfo.errors`, per ADR-0013.
    """
    order = SORT_ORDERS.get(sorting.sort_order)
    if sorting.sort_by != OppSortBy.CUSTOM and order is not None:
        spec = SortSpec(sorting.sort_by, order)
        return spec, {"sortBy": spec.sort_by, "sortOrder": spec.sort_order}

    if order is None:
        problem = (
            f'Sort order "{sorting.sort_order}" is not supported; use "asc" or "desc".'
        )
    else:
        problem = (
            f'Custom sort key "{sorting.custom_sort_by}" is not supported by this API.'
        )
    info: dict[str, Any] = {
        "sortBy": DEFAULT_SORT.sort_by,
        "sortOrder": DEFAULT_SORT.sort_order,
        "errors": [
            f"{problem} Results are sorted by lastModifiedAt descending instead.",
        ],
    }
    if sorting.custom_sort_by is not None:
        info["customSortBy"] = sorting.custom_sort_by
    return DEFAULT_SORT, info


def _resolve_filters(
    filters: OppFilters | None,
    search: str | None,
) -> tuple[OppDefaultFilters, dict[str, Any]]:
    """
    Split a filter request into the filters this API applies and a truthful `filterInfo`.

    Per ADR-0012 an unsupported custom filter is ignored and named in
    `filterInfo.errors`; `filterInfo.filters` lists only what was applied.
    """
    filters = filters or OppFilters()
    errors = [
        f'Custom filter "{name}" is not supported by this API and was ignored.'
        for name in filters.custom_filters or {}
    ]
    if search:
        errors.append(
            "Free-text search is not implemented by this API and was ignored.",
        )

    applied = OppDefaultFilters.model_validate(
        filters.model_dump(
            by_alias=True,
            exclude_unset=True,
            exclude={"custom_filters"},
        ),
    )
    info: dict[str, Any] = {
        "filters": applied.model_dump(by_alias=True, exclude_unset=True),
    }
    if errors:
        info["errors"] = errors
    return applied, info


@router.get(
    "",
    summary="List opportunities",
    description="Get a paginated list of opportunities, sorted by `lastModifiedAt` with "
    "most recent first.",
    response_model=OpportunitiesListResponse,
    response_model_exclude_unset=True,
    responses=ERROR_RESPONSES,
)
async def list_opportunities(
    repository: Repository,
    pagination: Annotated[PaginatedQueryParams, Query()],
) -> dict[str, Any]:
    """Return one page of opportunities, most recently modified first."""
    page = await repository.list(DEFAULT_SORT, pagination)
    return {
        "status": 200,
        "message": "Opportunities fetched successfully",
        "items": [_plain(o) for o in page.items],
        "paginationInfo": _pagination_info(page, pagination),
    }


@router.get(
    "/{oppId}",
    summary="View opportunity details",
    description="View details about an opportunity.",
    response_model=OpportunityResponse,
    response_model_exclude_unset=True,
    responses={
        404: {"model": Error, "description": "No opportunity has that id"},
        **ERROR_RESPONSES,
    },
)
async def get_opportunity(
    opp_id: Annotated[UUID, Path(alias="oppId")],
    repository: Repository,
) -> dict[str, Any]:
    """Return one opportunity by id."""
    opportunity = await repository.get(opp_id)
    if opportunity is None:
        raise OpportunityNotFoundError
    return {
        "status": 200,
        "message": "Opportunity fetched successfully",
        "data": _plain(opportunity),
    }


@router.post(
    "/search",
    summary="Search opportunities",
    description="Search for opportunities based on the provided filters.",
    response_model=OpportunitiesSearchResponse,
    response_model_exclude_unset=True,
    responses=ERROR_RESPONSES,
)
async def search_opportunities(
    repository: Repository,
    body: Annotated[OpportunitySearchRequest | None, Body()] = None,
) -> dict[str, Any]:
    """Return one page of the opportunities matching every applied filter."""
    body = body or OpportunitySearchRequest()
    sorting, sort_info = _resolve_sorting(body.sorting)
    filters, filter_info = _resolve_filters(body.filters, body.search)

    page = await repository.search(filters, sorting, body.pagination)
    return {
        "status": 200,
        "message": "Opportunities searched successfully",
        "items": [_plain(o) for o in page.items],
        "paginationInfo": _pagination_info(page, body.pagination),
        "sortInfo": sort_info,
        "filterInfo": filter_info,
    }
