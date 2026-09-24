# CommonGrants API template — FastAPI

A working [CommonGrants](https://commongrants.org) API you can run in about a
minute, then point at your own data.

It starts as a complete, self-contained service: three opportunity endpoints
backed by bundled sample data, every request and response validated with the
published [`common-grants-sdk`](https://pypi.org/project/common-grants-sdk/)
Pydantic models, and an OpenAPI 3.1 document generated from those same models
at `/openapi.json`, browsable in Swagger UI at `/docs`. Nothing is stubbed out
and nothing is left as an exercise — connecting your own data is one protocol
with three methods.

Built with [FastAPI](https://fastapi.tiangolo.com).

---

## Prerequisites

- **Python 3.11 or newer.** CI runs on 3.11, the version in
  [`.python-version`](.python-version). Use whichever installation or version
  manager you prefer.
- **[Poetry](https://python-poetry.org) 2.x** — the dependency manager. CI uses
  Poetry 2.5.1.
- **make** — the command runner. Every target is a thin wrapper around a
  Poetry command you can also run yourself.

No project-specific global packages, credentials, database or infrastructure
are required.

## Get started

Click **Use this template** at the top of
[this repository](https://github.com/common-grants/cg-api-template-fastapi) to
create your own, then:

```bash
git clone https://github.com/<you>/<your-api>.git
cd <your-api>
python3 --version # must report 3.11 or newer
poetry --version  # must report 2.x
make install
```

If Poetry picks up an older Python, point it at a newer one first with
`poetry env use python3.11`.

Check that everything works before you change anything:

```bash
make ci
```

That runs the format, lint and type checks, then the test suite with coverage.

Hosted CI runs that same pair of steps, then `make audit`.

Start the server:

```bash
make dev
```

Open <http://localhost:8000/docs> to browse the API in Swagger UI and try a
request from the browser. Or, in another terminal:

```bash
# A page of opportunities, most recently modified first
curl 'http://localhost:8000/common-grants/opportunities?pageSize=2'

# Filtered and sorted search
curl -X POST http://localhost:8000/common-grants/opportunities/search \
  -H 'Content-Type: application/json' \
  -d '{"filters":{"status":{"operator":"in","value":["open"]}},"sorting":{"sortBy":"title","sortOrder":"asc"}}'

# The OpenAPI 3.1 document, generated from the same models
curl http://localhost:8000/openapi.json
```

## Connect your own data

The bundled sample data lives behind a three-method protocol. Implement that
protocol against your database or upstream API and the routes, validation and
OpenAPI document all keep working unchanged.

**→ [PORTING.md](PORTING.md) is the walkthrough.** It covers replacing the
repository, mapping your ids onto stable UUIDs, handling date-valued fields in
filters and sorts, adding custom fields in one file, and which tests to keep.

## Endpoints

| Method | Path                                   | Description                                        |
| ------ | -------------------------------------- | -------------------------------------------------- |
| `GET`  | `/common-grants/opportunities`         | Paginated list, most recent `lastModifiedAt` first |
| `GET`  | `/common-grants/opportunities/{oppId}` | One opportunity by id                              |
| `POST` | `/common-grants/opportunities/search`  | Filtered, sorted, paginated search                 |
| `GET`  | `/health`                              | Liveness check                                     |
| `GET`  | `/openapi.json`                        | The OpenAPI 3.1 document                           |
| `GET`  | `/docs`                                | Swagger UI for the OpenAPI document                |

Every success body is validated by its `common-grants-sdk` response model
before it is sent, so repository output that drifts from the published shape
becomes a `500`, never a `200`. Requests that do not match their SDK model get
a `400`, and an unknown but well-formed id gets a `404`; every error body
validates against the SDK's `Error` model.

Pagination defaults come from the SDK's request models, as does the sort
direction when a search names a `sortBy` without a `sortOrder`.

The supported SDK range is `common-grants-sdk` `^0.8.1`: 0.8.1 up to, but not
including, 0.9.0. CI tests both ends. The `verify` job runs against the version
in `poetry.lock`, currently the floor of the range, and the `sdk-range` job
first updates the SDK to the newest release inside the range.

## Commands

| Command                     | What it does                                               |
| --------------------------- | ---------------------------------------------------------- |
| `make install`              | Install dependencies and the app into Poetry's environment |
| `make dev`                  | Start the server on port 8000 with reload on change        |
| `make test`                 | Run the test suite                                         |
| `make test-coverage`        | Run the tests with a coverage report                       |
| `make checks`               | Format check, lint and type check (never writes files)     |
| `make format` / `make lint` | Apply formatting and lint fixes                            |
| `make audit`                | The dependency audit                                       |
| `make ci`                   | The check and test suite: `checks`, then `test-coverage`   |
| `make gen-openapi`          | Write the OpenAPI document to `openapi.yaml`               |

`make audit` is deliberately separate from `make ci` and runs immediately
after it in hosted CI.

`poetry run fastapi run` serves the app without reload on `0.0.0.0`. Both it
and `make dev` read the port from `PORT`, defaulting to 8000.

## Structure

```
src/common_grants/
  api.py                 create_app(repository), error shaping and /health;
                         `app` is what `fastapi dev` and `fastapi run` serve
  constants.py           Your organization domain and the UUID namespace for stable ids
  routes/
    opportunities.py     Route handlers, SDK request and response models
  schemas/
    opportunity.py       The one opportunity model — add custom fields here
  services/
    repository.py        The data seam: list / get / search
    fixtures.py          Reference implementation over the bundled sample data
  data/
    opportunities.json   The bundled sample data
  scripts/
    generate_openapi.py  The OpenAPI export behind `make gen-openapi`
tests/                   pytest suites: app, routes, fixtures, OpenAPI
```

## Maintenance

This template is maintained by the [CommonGrants organization](https://github.com/common-grants).
File issues and pull requests here.

Projects created from this template are **independent**. There is no automatic
synchronization, no backports, and no source-maintainer responsibility for
derivative applications. You own your copy, including its dependency updates
and its `.github/` metadata — replace the issue templates and
contribution links with your own.

For how to keep your own copy current — and why updating your dependencies and
adopting template changes are two different jobs — see
[Keeping up to date](PORTING.md#8-keeping-up-to-date).

## Scope

This template is a starting point, not a framework. It deliberately ships
without deployment or auth recipes, a project generator, a live database
example, or release machinery. Add what your service needs.

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md)
and the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[CC0 1.0 Universal](LICENSE). Dependencies keep their own licenses.

This template began as the FastAPI template in
[HHS/simpler-grants-protocol](https://github.com/HHS/simpler-grants-protocol),
a work of the United States government.
