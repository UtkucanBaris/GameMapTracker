# Quality baseline

The local quality entry points are:

```powershell
uv run ruff check .
uv run mypy
uv run pytest
$env:QT_QPA_PLATFORM = "offscreen"; uv run pytest -m qt
uv run python tests/perf_harness.py --points 10000
```

Current verified results:

- `ruff check`: passes.
- `mypy`: passes for the configured domain/service files.
- `pytest`: 17 tests pass, including 5 Qt lifecycle/render tests.
- 10,000-point harness: completes successfully and reports accepted point,
  elapsed time and peak traced memory.
- `ruff format --check .`: still reports formatting changes in legacy files;
  the initial baseline intentionally did not apply a repository-wide formatter
  rewrite. New tests and `rendering_geometry.py` are formatted.
