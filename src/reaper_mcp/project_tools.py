import os
import time
import logging
from pathlib import Path

import reapy
from reapy import reascript_api as RPR

from reaper_mcp.connection import get_project

logger = logging.getLogger("reaper_mcp.project_tools")


def _get_time_signature(project) -> tuple[int, int]:
    """Return (numerator, denominator) for the project's initial time sig.

    reapy's `project.time_signature` returns (bpm, bpi) — NOT (num, denom).
    The numerator is the bpi, but the denominator isn't exposed by reapy at
    all. We read the first tempo/timesig marker directly for a full answer.
    """
    # EnumProjectMarkers won't give us the denominator; use the tempo marker
    # table. Marker 0 is the project's initial tempo/timesig.
    try:
        result = RPR.GetTempoTimeSigMarker(project.id, 0, 0, 0, 0, 0, 0, 0, False)
        # Returns (ok, proj, idx, timepos, measurepos, beatpos, bpm, timesig_num, timesig_denom, linear)
        if result and result[0]:
            num = int(result[7]) if result[7] else 4
            denom = int(result[8]) if result[8] else 4
            if num > 0 and denom > 0:
                return num, denom
    except Exception as e:
        logger.debug(f"GetTempoTimeSigMarker failed: {e}")

    # Fallback: bpi from reapy (this IS the numerator, even though reapy
    # confusingly returns (bpm, bpi)).
    try:
        _bpm, bpi = project.time_signature
        num = int(bpi) if bpi else 4
        return num, 4  # denominator unavailable — assume 4
    except Exception:
        return 4, 4


def _find_marker_at_start(project) -> int:
    """Return the index of the tempo/timesig marker at position 0, or -1 if
    none exists. Used to update (not duplicate) the initial marker."""
    try:
        result = RPR.GetTempoTimeSigMarker(project.id, 0, 0, 0, 0, 0, 0, 0, False)
        # result: (ok, proj, idx, timepos, measurepos, beatpos, bpm, num, denom, linear)
        if result and result[0] and float(result[3]) == 0.0:
            return 0
    except Exception:
        pass
    return -1


def _set_time_signature(project, numerator: int, denominator: int) -> None:
    """Set the project's initial time signature.

    reapy does not expose a setter for time_signature, so we write a tempo/
    time-signature marker at the start of the project. If a marker already
    exists at position 0 we UPDATE it (ptidx=0) rather than stacking a new
    one on top — stacking corrupts project.bpm readback on denom changes.

    NOTE: REAPER's SetTempoTimeSigMarker stores the tempo as
    `bpm * (denominator / 4)` internally (observed empirically on denom=8:
    passing 140 stored 280). We compensate by pre-dividing by that factor so
    project.bpm reads back as the caller expects.
    """
    current_bpm = project.bpm
    idx = _find_marker_at_start(project)
    compensated_bpm = current_bpm * 4.0 / float(denominator)
    # SetTempoTimeSigMarker(proj, ptidx, timepos, measurepos, beatpos, bpm,
    #                       timesig_num, timesig_denom, lineartempo)
    RPR.SetTempoTimeSigMarker(
        project.id, idx, 0.0, -1, -1, compensated_bpm, numerator, denominator, False
    )


def _set_tempo_preserving_timesig(project, bpm: float) -> None:
    """Set the project tempo. If a marker exists at position 0, update it in
    place (preserving the time signature). Otherwise fall back to the
    project.bpm setter.

    Compensates for REAPER's denominator-based tempo scaling in
    SetTempoTimeSigMarker (see note in _set_time_signature).
    """
    idx = _find_marker_at_start(project)
    if idx >= 0:
        result = RPR.GetTempoTimeSigMarker(project.id, idx, 0, 0, 0, 0, 0, 0, False)
        num = int(result[7]) if result and result[0] else 4
        denom = int(result[8]) if result and result[0] else 4
        compensated_bpm = bpm * 4.0 / float(denom)
        RPR.SetTempoTimeSigMarker(
            project.id, idx, 0.0, -1, -1, compensated_bpm, num, denom, False
        )
    else:
        project.bpm = bpm


def register_tools(mcp):

    @mcp.tool()
    def create_project(tempo: float = 120.0, time_signature: str = "4/4", name: str = "") -> dict:
        """Create a new REAPER project with the given tempo and time signature."""
        try:
            # Validate BEFORE we execute "File: New project", otherwise a bad
            # time signature string would leave the user with an empty new
            # project on top of their previous one.
            if not isinstance(tempo, (int, float)) or tempo <= 0:
                return {"success": False, "error": f"Invalid tempo: {tempo}"}

            num = denom = None
            if time_signature:
                try:
                    parts = time_signature.split("/")
                    if len(parts) != 2:
                        raise ValueError("expected format like '4/4'")
                    num, denom = int(parts[0]), int(parts[1])
                    if num <= 0 or denom <= 0:
                        raise ValueError("numerator and denominator must be positive")
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Invalid time_signature '{time_signature}': {e}",
                    }

            RPR.Main_OnCommand(41929, 0)  # File: New project
            project = get_project()
            project.bpm = tempo
            if num is not None and denom is not None:
                _set_time_signature(project, num, denom)
            return {
                "success": True,
                "name": name or f"New Project {time.strftime('%Y-%m-%d %H-%M-%S')}",
                "tempo": project.bpm,
                "time_signature": time_signature,
            }
        except Exception as e:
            logger.error(f"create_project failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def save_project(save_as_path: str = "") -> dict:
        """Save the current project.

        If the project was loaded from disk, it is saved back to its existing
        file path (no arguments needed). If the project is untitled, pass
        `save_as_path` — otherwise REAPER would pop a Save As dialog and this
        tool would hang.
        """
        try:
            project = get_project()
            # An untitled project has no name. Calling project.save() on an
            # untitled project triggers REAPER's Save As dialog and blocks
            # the reascript thread forever.
            if not project.name:
                if not save_as_path:
                    return {
                        "success": False,
                        "error": (
                            "Project is untitled — pass `save_as_path` with a "
                            "full file path (e.g. /path/to/my.RPP) to save."
                        ),
                    }
                target = str(Path(save_as_path).expanduser().resolve())
                os.makedirs(os.path.dirname(target), exist_ok=True)
                RPR.Main_SaveProjectEx(project.id, target, 0)
                return {"success": True, "saved_to": target}

            # Titled project — normal save.
            project.save()
            return {"success": True, "saved_to": project.path}
        except Exception as e:
            logger.error(f"save_project failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def load_project(project_path: str) -> dict:
        """Load a REAPER project (.rpp) from the given file path."""
        try:
            if not os.path.exists(project_path):
                return {"success": False, "error": f"File not found: {project_path}"}
            RPR.Main_openProject(project_path)
            project = get_project()
            num, denom = _get_time_signature(project)
            return {
                "success": True,
                "name": project.name,
                "tempo": project.bpm,
                "time_signature": f"{num}/{denom}",
                "project_path": project_path,
            }
        except Exception as e:
            logger.error(f"load_project failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_project_info() -> dict:
        """Get information about the current project: name, path, tempo, tracks, length."""
        try:
            project = get_project()

            # reapy's project.markers / project.regions both iterate the
            # combined marker+region table. Using range(n_markers) or
            # range(n_regions) as indices into that combined list can return
            # the wrong entity type and blow up on missing attributes.
            # Enumerate directly and filter defensively on the attributes that
            # distinguish markers (position) from regions (start/end).
            markers = []
            regions = []
            try:
                for i, m in enumerate(project.markers):
                    try:
                        if hasattr(m, "start") and hasattr(m, "end"):
                            regions.append({
                                "index": i,
                                "name": getattr(m, "name", ""),
                                "start": m.start,
                                "end": m.end,
                            })
                        else:
                            markers.append({
                                "index": i,
                                "name": getattr(m, "name", ""),
                                "position": getattr(m, "position", None),
                            })
                    except Exception as inner:
                        logger.debug(f"Skipping marker/region {i}: {inner}")
            except Exception as e:
                logger.debug(f"Could not enumerate markers/regions: {e}")

            num, denom = _get_time_signature(project)
            return {
                "success": True,
                "name": project.name,
                "path": project.path,
                "tempo": project.bpm,
                "time_signature": f"{num}/{denom}",
                "length": project.length,
                "track_count": project.n_tracks,
                "markers": markers,
                "regions": regions,
            }
        except Exception as e:
            logger.error(f"get_project_info failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_tempo(bpm: float) -> dict:
        """Set the project tempo in BPM."""
        try:
            project = get_project()
            _set_tempo_preserving_timesig(project, bpm)
            return {"success": True, "tempo": bpm}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_time_signature(numerator: int, denominator: int) -> dict:
        """Set the project time signature, e.g. 4/4, 3/4, 6/8."""
        try:
            if numerator <= 0 or denominator <= 0:
                return {
                    "success": False,
                    "error": "numerator and denominator must be positive",
                }
            project = get_project()
            _set_time_signature(project, numerator, denominator)
            num, denom = _get_time_signature(project)
            return {"success": True, "time_signature": f"{num}/{denom}"}
        except Exception as e:
            logger.error(f"set_time_signature failed: {e}")
            return {"success": False, "error": str(e)}
