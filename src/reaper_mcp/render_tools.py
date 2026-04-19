import os
import time
import logging
import tempfile
from pathlib import Path

import reapy
from reapy import reascript_api as RPR

from reaper_mcp.connection import get_project

logger = logging.getLogger("reaper_mcp.render_tools")

# REAPER RENDER_FORMAT codes
FORMAT_CODES = {
    "wav":  0,
    "mp3":  3,
    "ogg":  4,
    "flac": 5,
}

# REAPER RENDER_FORMAT2 codes for WAV bit depth
BIT_DEPTH_CODES = {
    16: 0,
    24: 2,
    32: 4,
}

# Render action 41824 is asynchronous on some REAPER builds — we poll for the
# output file to appear and stop growing before returning. These bounds keep
# the wait reasonable for normal projects.
_RENDER_POLL_INTERVAL = 0.25
_RENDER_INITIAL_TIMEOUT = 60.0   # seconds to wait for the file to appear
_RENDER_STABLE_CHECKS = 3        # consecutive equal sizes => render done
_RENDER_MAX_TOTAL = 600.0        # absolute upper bound (10 min)


def _set_render_settings(
    output_path: str,
    format: str,
    sample_rate: int,
    bit_depth: int,
    channels: int,
    bounds: int,
) -> None:
    """Configure REAPER's render settings.

    bounds: 0=custom time range, 1=entire project, 2=time selection,
            3=all project regions, 4=selected media items, 5=selected regions.
    """
    fmt_code = FORMAT_CODES.get(format.lower(), 0)
    bdepth_code = BIT_DEPTH_CODES.get(bit_depth, 2)
    # RENDER_FILE takes the directory, RENDER_PATTERN takes the filename
    directory = str(Path(output_path).parent)
    filename = Path(output_path).stem
    project = get_project()
    RPR.GetSetProjectInfo_String(project.id, "RENDER_FILE", directory, True)
    RPR.GetSetProjectInfo_String(project.id, "RENDER_PATTERN", filename, True)
    RPR.GetSetProjectInfo(project.id, "RENDER_FORMAT", fmt_code, True)
    RPR.GetSetProjectInfo(project.id, "RENDER_FORMAT2", bdepth_code, True)
    RPR.GetSetProjectInfo(project.id, "RENDER_SRATE", float(sample_rate), True)
    RPR.GetSetProjectInfo(project.id, "RENDER_CHANNELS", float(channels), True)
    RPR.GetSetProjectInfo(project.id, "RENDER_BOUNDSFLAG", float(bounds), True)


def _wait_for_render(output_path: str) -> bool:
    """Block until `output_path` exists and its size has been stable for
    several consecutive polls. Returns True on success, False on timeout."""
    start = time.time()
    appeared_at: float | None = None
    last_size = -1
    stable_count = 0

    while True:
        elapsed = time.time() - start
        if elapsed > _RENDER_MAX_TOTAL:
            logger.warning(f"Render exceeded max wait ({_RENDER_MAX_TOTAL}s): {output_path}")
            return False

        if not os.path.exists(output_path):
            if elapsed > _RENDER_INITIAL_TIMEOUT:
                logger.warning(
                    f"Render output never appeared within {_RENDER_INITIAL_TIMEOUT}s: {output_path}"
                )
                return False
            time.sleep(_RENDER_POLL_INTERVAL)
            continue

        if appeared_at is None:
            appeared_at = time.time()

        size = os.path.getsize(output_path)
        if size > 0 and size == last_size:
            stable_count += 1
            if stable_count >= _RENDER_STABLE_CHECKS:
                return True
        else:
            stable_count = 0
            last_size = size

        time.sleep(_RENDER_POLL_INTERVAL)


def _trigger_render_and_wait(output_path: str) -> bool:
    """Fire REAPER's 'render to disk (no dialog)' action and wait for the
    file to be fully written. Returns True on success."""
    # Remove any stale file at the target path so the polling loop doesn't
    # see a leftover and immediately call it "stable".
    try:
        if os.path.exists(output_path):
            os.unlink(output_path)
    except Exception as e:
        logger.warning(f"Could not remove stale render output {output_path}: {e}")

    RPR.Main_OnCommand(41824, 0)  # File: Render project to disk (no dialog)
    return _wait_for_render(output_path)


def render_to_temp_file(sample_rate: int = 48000) -> str:
    """
    Render the current project to a temporary WAV file and return its path.
    Blocks until the render finishes. Used by analysis and mastering tools.
    Caller is responsible for deleting the file.
    """
    # mkstemp is the secure, non-deprecated replacement for mktemp.
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    # REAPER will create the file itself; remove the empty placeholder so
    # the polling loop doesn't mistake it for a finished render.
    try:
        os.unlink(tmp)
    except Exception:
        pass

    _set_render_settings(tmp, "wav", sample_rate, 24, 2, bounds=1)
    if not _trigger_render_and_wait(tmp):
        raise RuntimeError(f"REAPER render did not complete or produced no output: {tmp}")
    return tmp


def register_tools(mcp):

    @mcp.tool()
    def render_project(
        output_path: str,
        format: str = "wav",
        sample_rate: int = 48000,
        bit_depth: int = 24,
        channels: int = 2,
    ) -> dict:
        """
        Render the entire project to a file.
        format: wav, flac, mp3 (requires LAME), ogg.
        sample_rate: e.g. 44100, 48000, 96000.
        bit_depth: 16, 24, or 32 (WAV only; ignored for mp3/ogg/flac).
        channels: 1 (mono) or 2 (stereo).
        """
        try:
            output_path = str(Path(output_path).expanduser().resolve())
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            _set_render_settings(output_path, format, sample_rate, bit_depth, channels, bounds=1)
            if not _trigger_render_and_wait(output_path):
                return {
                    "success": False,
                    "error": "Render did not finish writing to disk within the timeout",
                }
            return {
                "success": True,
                "output_path": output_path,
                "format": format,
                "sample_rate": sample_rate,
                "bit_depth": bit_depth,
                "channels": channels,
                "file_size_bytes": os.path.getsize(output_path),
            }
        except Exception as e:
            logger.error(f"render_project failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def render_time_selection(
        output_path: str,
        start: float,
        end: float,
        format: str = "wav",
        sample_rate: int = 48000,
        bit_depth: int = 24,
        channels: int = 2,
    ) -> dict:
        """Render a specific time range of the project to a file."""
        try:
            output_path = str(Path(output_path).expanduser().resolve())
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            project = get_project()
            project.time_selection = (start, end)
            _set_render_settings(output_path, format, sample_rate, bit_depth, channels, bounds=2)
            if not _trigger_render_and_wait(output_path):
                return {
                    "success": False,
                    "error": "Render did not finish writing to disk within the timeout",
                }
            return {
                "success": True,
                "output_path": output_path,
                "start": start,
                "end": end,
                "format": format,
                "file_size_bytes": os.path.getsize(output_path),
            }
        except Exception as e:
            logger.error(f"render_time_selection failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def render_stems(
        output_directory: str,
        track_indices: list = None,
        format: str = "wav",
        sample_rate: int = 48000,
        bit_depth: int = 24,
    ) -> dict:
        """
        Render each track as a separate stem file by soloing each track individually.
        track_indices: list of track indices, or null to render all tracks.
        Files are named after the track names in the output directory.
        """
        project = get_project()
        # Snapshot solo state BEFORE we touch anything so we can always
        # restore the user's mix exactly as it was.
        original_solo = []
        try:
            output_directory = str(Path(output_directory).expanduser().resolve())
            os.makedirs(output_directory, exist_ok=True)
            indices = track_indices if track_indices is not None else list(range(project.n_tracks))
            for j in range(project.n_tracks):
                original_solo.append(
                    RPR.GetMediaTrackInfo_Value(project.tracks[j].id, "I_SOLO")
                )

            rendered = []
            for idx in indices:
                track = project.tracks[idx]
                track_name = track.name or f"Track_{idx}"
                # Solo this track exclusively
                for j in range(project.n_tracks):
                    RPR.SetMediaTrackInfo_Value(
                        project.tracks[j].id, "I_SOLO", 2.0 if (j == idx) else 0.0
                    )
                # Sanitize filename
                safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in track_name)
                stem_path = os.path.join(output_directory, f"{safe_name}.{format}")
                # bounds=1 renders the entire project (soloed track audible);
                # the previous value of 0 (custom time range) produced empty
                # files because no custom range was set.
                _set_render_settings(stem_path, format, sample_rate, bit_depth, 2, bounds=1)
                completed = _trigger_render_and_wait(stem_path)
                rendered.append({
                    "track_index": idx,
                    "track_name": track_name,
                    "output_path": stem_path,
                    "exists": os.path.exists(stem_path),
                    "completed": completed,
                })

            return {
                "success": True,
                "output_directory": output_directory,
                "stems": rendered,
            }
        except Exception as e:
            logger.error(f"render_stems failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            # Always restore the user's original solo state, even if we errored.
            for j, v in enumerate(original_solo):
                try:
                    RPR.SetMediaTrackInfo_Value(project.tracks[j].id, "I_SOLO", v)
                except Exception:
                    pass
