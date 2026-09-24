# Contributing

Thanks for your interest in improving this template.

Before anything else, please read the [Code of Conduct](CODE_OF_CONDUCT.md).

> **Contributing to a project you generated from this template?** This file
> came along with the copy and points at _this_ repository. Replace it with
> your own guidance — see [PORTING.md §9](PORTING.md#9-before-you-ship).

## What belongs here

This repository is a **starting point**, not a framework. The best
contributions make the first hour easier or make the seams cleaner. Things that
are deliberately out of scope:

- deployment or auth recipes, a project generator
- a live database or upstream-API example
- release machinery, tags, changelogs
- protocol changes — those belong in
  [HHS/simpler-grants-protocol](https://github.com/HHS/simpler-grants-protocol)

If you are unsure whether an idea fits, open an issue before writing code.

## Reporting a bug

Open a [bug report](https://github.com/common-grants/cg-api-template-fastapi/issues/new/choose).
The most useful thing you can include is whether you saw it in a **fresh copy
of the template** or **after connecting your own data** — those are very
different problems.

## Development setup

You need Python 3.11 or newer and Poetry 2.x. CI runs Python 3.11, the version
in `.python-version`, with Poetry 2.5.1.

```bash
python3 --version # must report 3.11 or newer
poetry --version  # must report 2.x
make install
make ci
```

`make install` installs exactly what `poetry.lock` records. `make ci` is the
format, lint and type checks, then the test suite with coverage. Get it passing
before you open a pull request.

While you work:

| Command                     |                              |
| --------------------------- | ---------------------------- |
| `make dev`                  | Run the server with reload   |
| `make test`                 | Run the tests                |
| `make lint` / `make format` | Apply fixes                  |
| `make checks`               | Verify without writing files |

## Making a change

1. **Branch from `main`.**
2. **Write the test first.** Every behavior change needs a test that fails
   before your change and passes after.
3. **Keep the seams intact.** Route handlers own HTTP concerns — envelopes,
   defaults, status codes. The repository owns data access. Nothing
   HTTP-shaped should cross `src/common_grants/services/repository.py`.
4. **Use the shared model.** `src/common_grants/schemas/opportunity.py` is the
   single opportunity model. Response models, the fixture parser and the tests
   all read from it, which is what makes the one-file custom-field extension
   work. Do not import `OpportunityBase` directly elsewhere.
5. **Do not weaken validation to make something pass.** No `model_construct()`,
   no `type: ignore`, and no disabled rules to route around an error. The one
   exception is a rule-scoped `# pyright: ignore[...]` on a deliberate Pydantic
   field override, with a comment saying why. Every success body is
   re-validated by its SDK response model on purpose.
6. **Update the docs you invalidated.** A change to the data seam usually means
   a change to `PORTING.md`.

## Pull requests

Fill in the [pull request template](.github/pull_request_template.md), and say
in "Context for reviewers" **how you verified the change** — the actual
commands and their output, not "tested locally".

A pull request runs two CI jobs. The first installs from `poetry.lock`, runs
the checks, the tests with coverage, and `pip-audit --strict` over every
installed runtime _and_ development dependency. There are no excepted
advisories: any known vulnerability, and any package the audit cannot check,
blocks. The second updates `common-grants-sdk` to the newest release inside
the declared range and runs the tests against it.

A maintainer reviews every pull request. Nothing is auto-merged.

## Dependencies

Dependencies are reviewed deliberately rather than updated automatically. Keep
SDK updates separate from routine tooling and framework updates because they can
carry protocol changes.

## License

Contributions are accepted under [CC0 1.0 Universal](LICENSE). If you include
code from elsewhere, say so in the pull request and keep its notices intact.
