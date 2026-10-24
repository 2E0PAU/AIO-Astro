# Contributing

Use Python 3.12 or 3.13 and `uv sync --locked --dev`. Commit dependency changes
together with `uv.lock`. Source distributions and wheels can be built with `uv build`.

Before proposing a change, run:

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Keep changes focused and describe resulting behaviour and validation. New device
support belongs in an adapter behind a small domain contract. Protocol failures,
deadlines, cancellation and real image data handling deserve tests. Avoid tests
that merely restate UI labels or implementation details. GUI code should present
state and dispatch actions; services must remain usable from a terminal.

Coordinate units belong in names or typed models. Always use timezone-aware times
internally and UTC for exposure metadata. Never derive scientific data from a
stretched preview. Do not manufacture WCS headers from a planned target coordinate.

Use the simulator and local protocol peers during development. Describe any real
equipment validation with device model, server/driver versions, and observed
limitations. Protocol tests alone do not establish driver compatibility. Extend
the equipment matrix in `docs/ROADMAP.md` as devices are verified.

The project uses GPL-3.0-or-later. Preserve dependency notices and keep contributed
catalog data's provenance and redistribution terms explicit. Report issues with
reproduction steps and logs stripped of any private network or filesystem details.
