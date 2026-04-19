# Live Tool Test Results

**Date:** 2026-04-18
**Environment:** REAPER + reapy server running, MCP server with patched code (some tools still on stale schema until restart)

Legend: ✅ confirmed working live · ❌ broken (live) · ⚠️ works but with a quirk · 🆕 new bug not in original report · 🔁 needs server restart to verify

---

## Project Management (8 tools)

| Tool | Status | Notes |
|---|---|---|
| `create_project` | ✅ | Validates time_signature before File>New (B-17 fix) |
| `load_project` | ✅ | time_signature now reads correctly via tempo marker |
| `save_project` | 🔁 | Disk fix in place (save_as_path param, B-20). MCP server needs restart to pick up new schema. Old code still hangs on untitled. |
| `get_project_info` | ✅ | time_signature shows "4/4" / "7/8" correctly (B-9 + B-19) |
| `set_tempo` | ⚠️🆕 | B-22: stacked tempo markers cause project.bpm to read back as 256 after timesig changes. Patched on disk: now updates marker idx 0 in place. Needs restart. |
| `set_time_signature` | ✅ | "7/8" applied and read back correctly |
| `play_project` | ✅ | |
| `stop_transport` | ✅ | |
| `set_cursor_position` | ✅ | |

## Track Management (10 tools)

| Tool | Status | Notes |
|---|---|---|
| `create_track` | ✅ | audio / midi / instrument / folder all work |
| `list_tracks` | ✅ | |
| `get_track_info` | ✅ | volume_db / pan / muted / soloed all reflect changes |
| `rename_track` | ✅ | |
| `delete_track` | ✅ | track count decremented |
| `set_track_volume` | ✅ | -6 dB confirmed via get_track_info |
| `set_track_pan` | ✅ | -0.5 confirmed |
| `set_track_mute` | ✅ | toggles correctly |
| `set_track_solo` | ✅ | toggles correctly |
| `set_track_color` | ✅ | rgb(128,200,64) applied |

## Routing (4 tools)

| Tool | Status | Notes |
|---|---|---|
| `create_send` | ✅ | -6dB linear ≈ 0.501 confirmed |
| `list_sends` | ✅ | |
| `set_send_volume` | ✅ | -12dB linear ≈ 0.251 confirmed |
| `remove_send` | ✅ | sends array empty after |
| `create_bus` | ✅ | bus track created with sends from named sources |

## MIDI (4 tools)

| Tool | Status | Notes |
|---|---|---|
| `create_midi_item` | ✅ | |
| `add_midi_note` | ✅ | |
| `create_chord_progression` | ✅ | warnings[] surfaces unknown roots/types (B-8/B-16 fix) |
| `create_drum_pattern` | ✅ | empty pattern rejected with clear error (B-7 fix) |

## FX (10 tools)

| Tool | Status | Notes |
|---|---|---|
| `add_fx` | ✅ | ReaEQ, ReaComp added |
| `list_track_fx` | ✅ | |
| `bypass_fx` | ✅ | enabled flag flips correctly |
| `get_fx_parameters` | ✅ | range = [min, max] correctly (B-6 fix); Global Gain shows [0.0, 4.0] |
| `set_fx_parameter` | ✅ | normalized value applied + read back |
| `remove_fx` | ✅ | |
| `load_fx_preset` | ✅ | no crash; uses fx.preset (B-5 fix). Returns "" if preset not found. |
| `add_master_fx` | ✅ | ReaLimit added to master |
| `list_master_fx` | ✅ | |
| `set_master_fx_parameter` | ✅ | Threshold = 0.6 confirmed |

## Audio (5 tools)

| Tool | Status | Notes |
|---|---|---|
| `import_audio_file` | ✅ | wav imported, item.length = 7.75s |
| `edit_audio_item` (fade only) | ✅ | fade in/out via D_FADEINLEN/D_FADEOUTLEN (B-2 fix) |
| `edit_audio_item` (start_trim) | 🆕🔁 | B-21: take.start_offset has no setter. Patched on disk to use D_STARTOFFS via RPR. Needs restart. |
| `adjust_pitch` | ✅ | D_PITCH set + readback (B-3 fix) |
| `adjust_playback_rate` | ✅ | D_PLAYRATE set + readback (B-4 fix) |
| `start_recording` | 🔁 | Disk fix in place (I_RECARM, B-1). Skipped live test to avoid arming user's input chain. |

## Mixing / Automation (3 tools)

| Tool | Status | Notes |
|---|---|---|
| `set_master_volume` | ✅ | -3 dB applied, then restored to 0 |
| `add_volume_automation` | ✅ | point at t=1, -6 dB |
| `add_pan_automation` | ✅ | point at t=1, pan=0.5 |

## Rendering (3 tools)

| Tool | Status | Notes |
|---|---|---|
| `render_project` | ✅ | 7.75s wav, 2 MB output (B-11/B-12 fix) |
| `render_time_selection` | ✅ | 0–2s slice rendered, 530 KB |
| `render_stems` | ✅ | 3 stems rendered, solo state restored (B-13 fix) |

## Mastering (3 tools)

| Tool | Status | Notes |
|---|---|---|
| `apply_mastering_chain` | ✅ | "gentle" preset added EQ + Comp + Limiter to master |
| `apply_limiter` | ✅ | ReaLimit added at idx 4 |
| `normalize_project` | ✅ | Correctly returned "Project appears to be silent" — defensive check works |

## Analysis (6 tools)

| Tool | Status | Notes |
|---|---|---|
| `analyze_loudness` | ✅ | LUFS + true peak returned |
| `analyze_dynamics` | ✅ | RMS / peak / crest / DR returned |
| `analyze_frequency_spectrum` | ✅ | 7 bands returned |
| `analyze_stereo_field` | ✅ | width / correlation / mid&side returned |
| `analyze_transients` | ✅ | onset count + times returned |
| `detect_clipping` | ✅ | clipped sample count + peak returned |

---

## Summary

- **Live confirmed working:** 53 tools
- **Patched on disk, awaiting server restart to verify:** 4 tools
  - `save_project` (B-20 — needs new save_as_path param)
  - `set_tempo` (B-22 — tempo marker stacking)
  - `edit_audio_item` with start_trim (B-21 — D_STARTOFFS)
  - `start_recording` (B-1 — was patched earlier; not live-tested to avoid input arming)
- **Net new bugs found in live sweep:** B-21 (edit_audio_item start_offset), B-22 (tempo marker stacking)
- **Total bugs fixed across all sessions:** 22

## Next steps

1. Restart the MCP server (kill the running `reaper-mcp` process and re-launch) so it picks up the latest patches in `audio_tools.py` and `project_tools.py`.
2. Re-run these tools after restart:
   - `save_project(save_as_path="/tmp/test.RPP")` on an untitled project
   - `set_tempo(120)` after `set_time_signature(7, 8)` — readback should be 120, not 256
   - `edit_audio_item(track, item, start_trim=0.5)` — should succeed
3. Manually verify `start_recording` once you're ready to arm an input.
