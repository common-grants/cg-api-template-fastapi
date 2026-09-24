"""
The application factory.

`create_app()` builds the whole API from one dependency, an
`OpportunityRepository`, and never opens a socket. The test suite and the
OpenAPI export both build apps this way.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, Request

from common_grants.services.fixtures import fixture_repository
from common_grants.services.repository import OpportunityRepository


def get_repository(request: Request) -> OpportunityRepository:
    """FastAPI dependency that yields the repository the app was built with."""
    return request.app.state.repository


Repository = Annotated[OpportunityRepository, Depends(get_repository)]


def create_app(repository: OpportunityRepository) -> FastAPI:
    """Build the CommonGrants API over any repository implementation."""
    app = FastAPI()
    app.state.repository = repository
    return app


# The app `fastapi dev` and `fastapi run` serve. Swap the repository here.
app = create_app(fixture_repository)
