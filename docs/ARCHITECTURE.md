# Architecture and runtime contracts

## Data flow

`MemoryReader` reads finite X/Y floats from the Win32 process. `PollingService`
emits them through Qt signals. `MainWindow` passes accepted samples to
`TrailModel`; the model owns paths, POIs and painted segment data. The
`GraphRenderer` consumes that model and owns only scene/render state.

```text
Exanima memory
    -> MemoryReader
    -> PollingService.value_read
    -> MainWindow
    -> TrailModel.add
    -> GraphRenderer.add_trail_point
```

## Timer lifecycle

- The polling timer runs at the selected interval while recording.
- When idle threshold is reached, the polling timer stops but a low-frequency
  watchdog continues reading. A changed coordinate restores the normal timer
  and emits `idle_resumed`.
- The renderer follow timer is started only while recording or follow is
  enabled. `MainWindow.closeEvent()` calls `GraphRenderer.shutdown()`.
- Window close also stops the bounds-sync timer, polling service, hotkey
  filter and Win32 reader before persistence.

## Rendering contracts

- `TrailModel.paths` is the source of truth.
- Accepted recording points use `add_trail_point()`; the polling hot path does
  not call full `render()`.
- Full rebuilds are reserved for view/data changes and debounced bounds
  synchronization.
- `_trail_pts` keeps at most 2048 recent screen points for follow-zoom
  calculations. Recording dot items are capped at 4096; the model still keeps
  the complete trail for stop, save and export.
- `preserve_transform=True` must not reset the user's pan/zoom state.
- Teleports finalize the active scene path, start a new colored path, snap the
  marker, and reset the live tail anchor.

## Data validation

Live samples, imported text, persisted trail points and POIs must be finite.
Invalid persisted/imported points are skipped. The `MapCalibration` incomplete
state intentionally uses NaN sentinels and is validated separately.

## Canonical checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
$env:QT_QPA_PLATFORM = "offscreen"; uv run pytest -m qt
uv run python tests/perf_harness.py --points 10000
```
