"""Tests for the application factory."""

from fastapi import FastAPI

from common_grants.api import create_app
from tests.support import StubRepository, as_repository


def test_create_app_accepts_any_repository():
    """Constructing the app has no side effects and takes the seam as its only input."""
    app = create_app(as_repository(StubRepository()))
    assert isinstance(app, FastAPI)
