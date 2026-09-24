# Connect your own data

The starter runs against bundled sample data. This is how you replace it.

The data model lives in `src/common_grants/schemas/` and the repository in
`src/common_grants/services/`. The routes, the request and response
validation, and the OpenAPI document are all derived from the SDK models —
they do not need to know where the data came from.

---

## 1. Implement the repository protocol

`src/common_grants/services/repository.py` defines the seam:

```python
class OpportunityRepository(Protocol):
    async def list(self, sorting: SortSpec, pagination: PaginatedBase) -> Page: ...
    async def get(self, opp_id: UUID) -> Opportunity | None: ...
    async def search(
        self,
        filters: OppDefaultFilters,
        sorting: SortSpec,
        pagination: PaginatedBase,
    ) -> Page: ...
```

It is a `typing.Protocol`, so your class does not need to inherit from it; it
only has to have these three methods. Three things are worth knowing before you
write yours:

- **Nothing HTTP-shaped crosses this boundary.** No envelopes, no status
  codes, no request objects. Return models and a total count in a `Page`; the
  routes build the response.
- **`pagination` is already validated.** `page` and `page_size` are positive
  integers with the SDK's defaults applied by the time they reach you.
- **`sorting` is already resolved.** `sort_by` is a key you can execute and
  `sort_order` is `"asc"` or `"desc"`. Implementation-defined sort keys never
  reach you; the routes fall back to the default order and report that in
  `sortInfo.errors`. The list route hands `list` its default order the same
  way, so your repository never has to know what that default is.

`src/common_grants/services/fixtures.py` is the reference implementation. Read
it before you write yours — it shows what real filtering, sorting and paging
have to handle, including the parts that are easy to get wrong (see §4 and §5).

Then wire it up in `src/common_grants/api.py`:

```diff
-from common_grants.services.fixtures import fixture_repository
+from common_grants.services.postgres import PostgresRepository

-app = create_app(fixture_repository)
+app = create_app(PostgresRepository(os.environ["DATABASE_URL"]))
```

Read the connection string from the environment, and fail at startup when it
is missing rather than on the first query — `os.environ["DATABASE_URL"]` raises
at import time, before the server accepts a request. Put it in `.env`, which is
already gitignored (`.env.example` shows the shape), and load it into your shell
with `set -a; . ./.env; set +a` before `make dev`.

Delete `services/fixtures.py`, `data/opportunities.json` and
`tests/test_fixtures.py` once nothing imports them.

## 2. Map your ids onto stable UUIDs

`Opportunity.id` is a UUID, and it is the public identity of the record: it
appears in `GET /common-grants/opportunities/{oppId}`, so consumers will store
it, bookmark it and use it as a foreign key.

**The same source record must always produce the same UUID.** If your system
uses integer or string keys, do not generate a random UUID per request or per
import. Either:

- store a generated UUID alongside each record the first time you see it, and
  read it back afterwards, or
- derive one deterministically from your key. `src/common_grants/constants.py`
  sets this up: replace `ORGANIZATION_DOMAIN` with your own domain, then use
  `uuid.uuid5(OPPORTUNITY_NAMESPACE, str(row.id))`.

Changing `ORGANIZATION_DOMAIN` later changes every derived id, so set it once
before you publish.

Keep the original key too. `customFields` is a good home for it (see §6), and
it is what lets you trace a CommonGrants id back to your own system.

## 3. Return parsed models, not raw rows

Your repository returns `Opportunity` instances. Date fields are real `date`
and `datetime` objects, money amounts are strings, and nested objects are
models.

The simplest correct implementation parses your rows through the model:

```python
from common_grants.schemas.opportunity import Opportunity

rows = await db.fetch(...)
items = [Opportunity.model_validate(to_common_grants(row)) for row in rows]
```

If a row cannot be parsed you find out at the source, with a Pydantic error
location pointing at the field. Avoid `model_construct()` and
`model_copy(update=...)`, which skip validation: the routes re-validate every
response and answer `500` when a record does not match — correct, but much
harder to debug.

## 4. Date-valued fields in filters and sorts

Two date shapes appear in the protocol and they behave differently:

| Field                                     | Python type | Serializes as          |
| ----------------------------------------- | ----------- | ---------------------- |
| `createdAt`, `lastModifiedAt`             | `datetime`  | `2026-02-12T14:30:00Z` |
| `keyDates.*.date`, `startDate`, `endDate` | `date`      | `2026-03-31`           |

**Give every `datetime` a timezone.** A naive `datetime` serializes without an
offset (`2026-02-12T14:30:00`), which is not a valid OpenAPI `date-time`.
Attach `timezone.utc` when you read timestamps that your database stores
without one.

For sorting and range filters, compare the `date` or `datetime` objects, not
their strings. `closeDateRange` bounds arrive as `date` objects and both ends
of a `between` range are inclusive. The SDK lets a client omit either bound;
the fixtures treat a missing or inverted bound as matching nothing, the same
way they treat a record with no close date. Decide what your API does and test
it.

## 5. Money is a decimal string

`Money.amount` is a `str`, not a number, so that no precision is lost in
transit. Comparing those strings directly gives you lexical order:
`"9000.00" > "10000.00"`. Convert with `decimal.Decimal` before you compare or
sort — never `float`, which rounds — or push the comparison into SQL with a
numeric cast. See `_money_matches()` in `services/fixtures.py`.

`funding.estimatedAwardCount` and the other counts _are_ integers, so mixing
the two is the easy mistake.

Currency is part of the comparison. A money-range filter names a currency on
both bounds, and Core's filter descriptions say amounts in a different currency
are excluded from the search. The fixtures apply that to `outside` as well as
`between`: without a rate the amounts are not comparable, so the record is
unknown relative to the range, like a missing value, rather than outside it.
If your data holds several currencies, decide whether to convert or keep this
rule, and test it either way.

## 6. Add custom fields in one file

`src/common_grants/schemas/opportunity.py` is the single definition of the
opportunity model. The response models, the repository's types, the fixture
parser and the OpenAPI document all read from it, so extending it extends all
of them at once.

It does not change this template's request models: the list, get and search
requests carry pagination, filters, sorting and an id, none of which embed the
opportunity model. Custom fields reach the wire through opportunity **response**
data and its OpenAPI definitions.

```python
from common_grants_sdk.extensions.specs import CustomFieldSpec
from common_grants_sdk.schemas.pydantic import CustomFieldType, OpportunityBase
from pydantic import BaseModel


class LegacyId(BaseModel):
    system: str
    id: int


class Opportunity(
    OpportunityBase.with_custom_fields(
        custom_fields={
            "legacyId": CustomFieldSpec(
                field_type=CustomFieldType.OBJECT,
                value=LegacyId,
                description="Maps to the opportunity_id in the legacy system",
            ),
            "category": CustomFieldSpec(
                field_type=CustomFieldType.STRING,
                value=str,
                description="Grant category",
            ),
        },
        model_name="Opportunity",
    ),
):
    """The opportunity model this API serves."""
```

That is the whole change. Afterwards:

- `opp.custom_fields.legacy_id.value.id` is an `int` at runtime; keys become
  snake_case attributes. `opp.get_custom_field_value("legacyId", LegacyId)`
  reads the same value by its wire name.
- A custom field of the wrong type is rejected at parse time, with the error
  location pointing into `customFields`.
- The custom fields appear in the opportunity response definitions in
  `/openapi.json` with their real value schemas.
- Routes, handlers and the repository protocol are untouched.

Keep the `class` statement. The website's custom-fields guide assigns the
result instead (`Opportunity = OpportunityBase.with_custom_fields(...)`), which
works at runtime but makes `Opportunity` a variable, and pyright then rejects
every annotation that uses it, so `make check-types` fails. The class keeps it
a type. `with_custom_fields` builds the model at runtime, so a type checker
sees the custom fields as untyped either way.

## 7. Tests

The four suites divide along the seam:

| Suite                         | Keep or replace                                                                                  |
| ----------------------------- | ------------------------------------------------------------------------------------------------ |
| `tests/test_app.py`           | **Keep.** Health, 404, 405, malformed JSON and error shaping — no fixture data involved.          |
| `tests/test_opportunities.py` | **Keep.** Drives the routes with a stub repository, so it never mentions a fixture id or count.  |
| `tests/test_openapi.py`       | **Keep**, and extend the operation list if you add routes.                                       |
| `tests/test_fixtures.py`      | **Replace.** Every assertion is about the bundled sample data.                                   |

Write the replacement for your repository against the same checklist the
fixture suite covers, because these are the cases that break in production:

- an empty page past the end, and the total staying correct
- both ends of a `between` range, inclusive
- records with **no value** for a filtered or sorted field
- ties on the sort key — pick a deterministic tie-break and test it, otherwise
  paging can show or skip a record
- money compared numerically rather than lexically
- both sort directions, including on date-valued keys

Then add at least one integration test that runs your real repository against a
real (test) data store. The route tests prove the contract; only an integration
test proves your mapping.

## 8. Keeping up to date

Two different things, often confused:

**Your dependencies.** Your project's problem, on your schedule. The
`common-grants-sdk` releases are the ones to watch, because they carry
protocol changes: <https://github.com/HHS/simpler-grants-protocol/releases>.
Review SDK updates separately from routine tooling and framework updates so the
protocol-relevant change stays visible. The `sdk-range` job in
`.github/workflows/ci.yml` runs the tests against the newest SDK release your
`pyproject.toml` range allows, so a new release shows up there before you lock
it.

**The template itself.** A project created from a GitHub template has no
ongoing link to its source. There is no automatic synchronization, no
backports, and no obligation on the template's maintainers toward your
application. If you want a later improvement, look at the template's commit
history and cherry-pick it deliberately:
<https://github.com/common-grants/cg-api-template-fastapi/commits/main>.

## 9. Before you ship

- Replace the issue templates and the pull-request
  template with your own — the ones you inherited point at this template's
  maintainers.
- Review `.github/workflows/ci.yml` and adapt it to your own branch and
  dependency policies.
- Update `name`, `description` and `license` in `pyproject.toml`, and the
  `title`, `version` and `description` passed to the app in
  `src/common_grants/api.py`, which title your OpenAPI document.
- Set `ORGANIZATION_DOMAIN` in `src/common_grants/constants.py` if you derive
  ids from it (§2).
- FastAPI's `/docs` loads Swagger UI from a CDN by default (jsdelivr, floating
  within swagger-ui-dist 5.x). For a locked-down deployment, self-host the
  assets or point the docs page at a mirror; FastAPI documents both in
  [Custom Docs UI Static Assets](https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/).
