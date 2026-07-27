# Manual regression checklist

Run after map/camera/render changes. Pan and zoom to a non-default view first, then perform each action. **Pass** = map center and zoom level stay the same (no jump); trail data still correct.

## View stability (`preserve_transform`)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Load trail + map, pan/zoom away from fit | Baseline view |
| 2 | Toggle **Fade Trail** | View unchanged |
| 3 | Toggle **Heat Map** | View unchanged |
| 4 | Click **Smooth** (not recording) | View unchanged |
| 5 | Add / edit / delete **POI** | View unchanged |
| 6 | Toggle **POI Path Highlight** (with POIs) | View unchanged; highlights only near POIs |
| 7 | **Stop** after recording | View unchanged; dots/lines match list |

## Live recording

| Step | Action | Expected |
|------|--------|----------|
| 8 | **Start** recording, walk 15s straight | Red live marker; blue dots appear before stop |
| 9 | **Zoom Follow** on while moving | Dots stay visible size; trail not paper-thin |
| 10 | Idle (no move) with Auto Follow on | Manual pan works until you move again |

## POI highlights

| Step | Action | Expected |
|------|--------|----------|
| 11 | Highlight **off** while recording | No colored overlay on path |
| 12 | Highlight **on** after stop, loop POI in center | Only nearest ring segments colored, not whole map |

## Manual trail paint

| Step | Action | Expected |
|------|--------|----------|
| 13 | Select **POI** in list, enable **Paint Trail**, drag on loop | Segments under brush use POI category color |
| 14 | **Erase** on, drag painted area | Color removed |
| 15 | Restart app | Painted segments restored from `trail.json` |

## Lifecycle and long-session checks

| Step | Mode | Action | Expected |
|------|------|--------|----------|
| 16 | SEMI-AUTO | Start, then Stop; wait 10 seconds | No new memory reads, live marker/labels do not reappear |
| 17 | SEMI-AUTO | Set Idle threshold, stop moving, then move again | Status changes to idle, then resumes and records the movement |
| 18 | MANUAL-WINDOWS | Close the window while recording | Polling, follow timer, hotkeys and process handle are released without an error |
| 19 | SEMI-AUTO | Record/import a 10k+ point trail with Zoom Follow | View remains usable; incremental trail and smooth marker remain visible |
| 20 | MANUAL-WINDOWS | Toggle Auto Follow/Zoom Follow and manually pan | Follow pauses on manual pan and resumes after meaningful movement |

## Verification modes

- **AUTO:** `uv run pytest` veya `QT_QPA_PLATFORM=offscreen uv run pytest -m qt`.
- **SEMI-AUTO:** Fake data/offscreen testinden sonra kısa kullanıcı doğrulaması.
- **MANUAL-WINDOWS:** Exanima ve gerçek F8/F10/native window lifecycle ile doğrulama.
