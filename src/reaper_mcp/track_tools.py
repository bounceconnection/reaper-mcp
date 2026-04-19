import math
import logging

import reapy
from reapy import reascript_api as RPR

from reaper_mcp.connection import get_project

logger = logging.getLogger("reaper_mcp.track_tools")


def _vol_to_db(vol_linear: float) -> float:
    """Convert REAPER linear volume (D_VOL) to dB."""
    if vol_linear <= 0:
        return -150.0
    return 20.0 * math.log10(vol_linear)


def _db_to_vol(db: float) -> float:
    """Convert dB to REAPER linear volume (D_VOL)."""
    return 10.0 ** (db / 20.0)


def _get_track_volume_db(track) -> float:
    return round(_vol_to_db(track.get_info_value("D_VOL")), 2)


def _get_track_pan(track) -> float:
    return round(track.get_info_value("D_PAN"), 4)


def _get_item_name(item) -> str:
    """Get item name from active take, with fallback."""
    try:
        take = item.active_take
        if take is not None:
            return take.name
    except Exception:
        pass
    return ""


def register_tools(mcp):

    @mcp.tool()
    def create_track(name: str, track_type: str = "audio") -> dict:
        """
        Create a new track at the end of the project.
        track_type: audio, midi, instrument, folder
        """
        try:
            project = get_project()
            idx = project.n_tracks
            project.add_track(idx, name)
            track = project.tracks[idx]

            if track_type in ("midi", "instrument"):
                RPR.SetMediaTrackInfo_Value(track.id, "I_RECINPUT", 4096)  # All MIDI inputs
            elif track_type == "folder":
                RPR.SetMediaTrackInfo_Value(track.id, "I_FOLDERDEPTH", 1)

            return {
                "success": True,
                "track_index": idx,
                "name": track.name,
                "type": track_type,
            }
        except Exception as e:
            logger.error(f"create_track failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def delete_track(track_index: int) -> dict:
        """Delete a track by its index."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            RPR.DeleteTrack(track.id)
            return {"success": True, "deleted_index": track_index}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def rename_track(track_index: int, name: str) -> dict:
        """Rename a track."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            track.name = name
            return {"success": True, "track_index": track_index, "name": track.name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_track_volume(track_index: int, volume_db: float) -> dict:
        """Set track volume in dB. Range: roughly -150 to +12 dB."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            track.set_info_value("D_VOL", _db_to_vol(volume_db))
            return {"success": True, "track_index": track_index, "volume_db": _get_track_volume_db(track)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_track_pan(track_index: int, pan: float) -> dict:
        """Set track pan. -1.0 = full left, 0.0 = center, 1.0 = full right."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            track.set_info_value("D_PAN", pan)
            return {"success": True, "track_index": track_index, "pan": _get_track_pan(track)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_track_mute(track_index: int, muted: bool) -> dict:
        """Mute or unmute a track."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            RPR.SetMediaTrackInfo_Value(track.id, "B_MUTE", 1.0 if muted else 0.0)
            return {"success": True, "track_index": track_index, "muted": bool(track.get_info_value("B_MUTE"))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_track_solo(track_index: int, soloed: bool) -> dict:
        """Solo or unsolo a track."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            RPR.SetMediaTrackInfo_Value(track.id, "I_SOLO", 2.0 if soloed else 0.0)
            return {"success": True, "track_index": track_index, "soloed": bool(track.get_info_value("I_SOLO"))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_track_info(track_index: int) -> dict:
        """Get detailed information about a track including FX and items."""
        try:
            project = get_project()
            track = project.tracks[track_index]

            fx_list = []
            for i in range(track.n_fxs):
                fx = track.fxs[i]
                fx_list.append({"index": i, "name": fx.name, "enabled": fx.is_enabled})

            items = []
            for i in range(track.n_items):
                item = track.items[i]
                items.append({
                    "index": i,
                    "position": item.position,
                    "length": item.length,
                    "name": _get_item_name(item),
                })

            return {
                "success": True,
                "track_index": track_index,
                "name": track.name,
                "volume_db": _get_track_volume_db(track),
                "pan": _get_track_pan(track),
                "muted": track.is_muted,
                "soloed": track.is_solo,
                "fx_count": track.n_fxs,
                "fx": fx_list,
                "item_count": track.n_items,
                "items": items,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def list_tracks() -> dict:
        """List all tracks in the current project with their basic parameters."""
        try:
            project = get_project()
            tracks = []
            for i in range(project.n_tracks):
                track = project.tracks[i]
                tracks.append({
                    "index": i,
                    "name": track.name,
                    "volume_db": _get_track_volume_db(track),
                    "pan": _get_track_pan(track),
                    "muted": track.is_muted,
                    "soloed": track.is_solo,
                    "fx_count": track.n_fxs,
                    "item_count": track.n_items,
                })
            return {"success": True, "count": len(tracks), "tracks": tracks}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_track_color(track_index: int, r: int, g: int, b: int) -> dict:
        """Set track color using RGB values (0–255 each)."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            color = RPR.ColorToNative(r, g, b) | 0x1000000
            RPR.SetMediaTrackInfo_Value(track.id, "I_CUSTOMCOLOR", color)
            return {"success": True, "track_index": track_index, "r": r, "g": g, "b": b}
        except Exception as e:
            return {"success": False, "error": str(e)}
