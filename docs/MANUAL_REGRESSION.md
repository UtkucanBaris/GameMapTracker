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
