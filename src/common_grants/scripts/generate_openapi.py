"""Print the served OpenAPI document as YAML; `make gen-openapi` writes openapi.yaml."""

import sys

import yaml

from common_grants.api import create_app
from common_grants.services.fixtures import fixture_repository


def main() -> None:
    """Write the document the app serves at /openapi.json to stdout."""
    document = create_app(fixture_repository).openapi()
    yaml.safe_dump(document, sys.stdout, sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    main()
