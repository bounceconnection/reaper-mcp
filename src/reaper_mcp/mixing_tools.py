import logging

import reapy
from reapy import reascript_api as RPR

from reaper_mcp.connection import get_project

logger = logging.getLogger("reaper_mcp.mixing_tools")


def _db_to_linear(db: float) -> float:
    if db <= -150:
        return 0.0
    return 10 ** (db / 20.0)


def _scale_to_envelope(envelope, natural_value: float) -> float:
    """Convert a 'natural' value (linear amplitude for volume, -1..1 for pan)
    into the envelope's native internal representation.

    REAPER envelopes can be in either 'no scaling' (mode 0 — raw natural
    value) or 'fader scaling' (mode 1 — fader-curve-mapped). InsertEnvelopePoint
    expects values in the envelope's native units, not natural units. Skipping
    this conversion is what causes "two points at +1 dB rendering as silence"
    in fader-scaling mode: the raw 1.122 gets interpreted as a fader position,
    and the static fader is overridden by the envelope.
    """
    try:
        mode = RPR.GetEnvelopeScalingMode(envelope)
        if mode:
            return RPR.ScaleToEnvelopeMode(mode, natural_value)
    except Exception as e:
        logger.debug(f"ScaleToEnvelopeMode unavailable, using raw value: {e}")
    return natural_value


def _ensure_envelope(track, env_name: str, toggle_action_id: int):
    """Return the named track envelope, creating/showing it if it doesn't
    already exist. A freshly-visible envelope is what gets serialized into
    the track state chunk on save — without this, InsertEnvelopePoint writes
    to a phantom envelope that affects render but not save_project.
    """
    env = RPR.GetTrackEnvelopeByName(track.id, env_name)
    if env:
        return env
    # Select only this track so the "toggle envelope visible" action targets it.
    RPR.SetOnlyTrackSelected(track.id)
    RPR.Main_OnCommand(toggle_action_id, 0)
    return RPR.GetTrackEnvelopeByName(track.id, env_name)


def register_tools(mcp):

    @mcp.tool()
    def add_volume_automation(track_index: int, position: float, value_db: float) -> dict:
        """Add a volume automation point on a track.

        If the track's Volume envelope isn't visible yet, it is auto-toggled
        visible (REAPER action 40406) so the points persist through save.

        position: time in seconds. value_db: volume level in dB.
        """
        try:
            project = get_project()
            track = project.tracks[track_index]
            # 40406 = "Track: Toggle track volume envelope visible"
            envelope = _ensure_envelope(track, "Volume", 40406)
            if not envelope:
                return {
                    "success": False,
                    "error": (
                        "Could not find or create the Volume envelope. Make sure "
                        "the track exists and is not locked."
                    ),
                }
            linear_val = _db_to_linear(value_db)
            env_val = _scale_to_envelope(envelope, linear_val)
            RPR.InsertEnvelopePoint(envelope, position, env_val, 0, 0, False, True)
            RPR.Envelope_SortPoints(envelope)
            return {"success": True, "track_index": track_index, "position": position, "value_db": value_db}
        except Exception as e:
            logger.error(f"add_volume_automation failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def add_pan_automation(track_index: int, position: float, pan: float) -> dict:
        """Add a pan automation point on a track.

        If the Pan envelope isn't visible yet, it is auto-toggled visible
        (REAPER action 40407) so the points persist through save.

        pan: -1.0 (full left) to 1.0 (full right).
        """
        try:
            project = get_project()
            track = project.tracks[track_index]
            # 40407 = "Track: Toggle track pan envelope visible"
            envelope = _ensure_envelope(track, "Pan", 40407)
            if not envelope:
                return {
                    "success": False,
                    "error": (
                        "Could not find or create the Pan envelope. Make sure "
                        "the track exists and is not locked."
                    ),
                }
            env_val = _scale_to_envelope(envelope, pan)
            RPR.InsertEnvelopePoint(envelope, position, env_val, 0, 0, False, True)
            RPR.Envelope_SortPoints(envelope)
            return {"success": True, "track_index": track_index, "position": position, "pan": pan}
        except Exception as e:
            logger.error(f"add_pan_automation failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def create_send(
        source_track_index: int, dest_track_index: int, volume_db: float = 0.0
    ) -> dict:
        """Create an aux send from one track to another."""
        try:
            project = get_project()
            src = project.tracks[source_track_index]
            dst = project.tracks[dest_track_index]
            send_idx = RPR.CreateTrackSend(src.id, dst.id)
            if send_idx < 0:
                return {"success": False, "error": "Failed to create send"}
            RPR.SetTrackSendInfo_Value(src.id, 0, send_idx, "D_VOL", _db_to_linear(volume_db))
            return {
                "success": True,
                "source_track_index": source_track_index,
                "dest_track_index": dest_track_index,
                "send_index": send_idx,
                "volume_db": volume_db,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def list_sends(track_index: int) -> dict:
        """List all sends from a track."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            n = RPR.GetTrackNumSends(track.id, 0)
            sends = []
            for i in range(n):
                vol = RPR.GetTrackSendInfo_Value(track.id, 0, i, "D_VOL")
                pan = RPR.GetTrackSendInfo_Value(track.id, 0, i, "D_PAN")
                muted = bool(RPR.GetTrackSendInfo_Value(track.id, 0, i, "B_MUTE"))
                sends.append({"send_index": i, "volume_linear": vol, "pan": pan, "muted": muted})
            return {"success": True, "track_index": track_index, "sends": sends}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def remove_send(source_track_index: int, send_index: int) -> dict:
        """Remove a send from a track by its index."""
        try:
            project = get_project()
            track = project.tracks[source_track_index]
            RPR.RemoveTrackSend(track.id, 0, send_index)
            return {"success": True, "source_track_index": source_track_index, "send_index": send_index}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_send_volume(source_track_index: int, send_index: int, volume_db: float) -> dict:
        """Set the volume of a send in dB."""
        try:
            project = get_project()
            track = project.tracks[source_track_index]
            RPR.SetTrackSendInfo_Value(track.id, 0, send_index, "D_VOL", _db_to_linear(volume_db))
            return {
                "success": True,
                "source_track_index": source_track_index,
                "send_index": send_index,
                "volume_db": volume_db,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def create_bus(name: str, track_indices: list) -> dict:
        """
        Create a new bus track and route the given tracks to it via sends.
        track_indices: list of track indices to feed into the bus.
        """
        try:
            project = get_project()
            bus_idx = project.n_tracks
            project.add_track(bus_idx, name)
            bus_track = project.tracks[bus_idx]
            sends = []
            for idx in track_indices:
                src = project.tracks[idx]
                send_i = RPR.CreateTrackSend(src.id, bus_track.id)
                sends.append({"track_index": idx, "send_index": send_i})
            return {
                "success": True,
                "bus_index": bus_idx,
                "bus_name": name,
                "sends": sends,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
