import logging

import reapy
from reapy import reascript_api as RPR

from reaper_mcp.connection import get_project

logger = logging.getLogger("reaper_mcp.fx_tools")


def register_tools(mcp):

    @mcp.tool()
    def add_fx(track_index: int, fx_name: str) -> dict:
        """
        Add an FX plugin to a track. Works for both instruments (VSTi) and effects (VST/AU).
        Use the exact plugin name as shown in REAPER's FX browser.
        Built-in Cockos plugins: ReaEQ, ReaComp, ReaDelay, ReaVerb, ReaLimit, ReaSynth,
        ReaSamplOmatic5000, ReaTune, ReaGate, ReaFIR, ReaXcomp.
        """
        try:
            project = get_project()
            track = project.tracks[track_index]
            fx = track.add_fx(fx_name)
            fx_idx = list(track.fxs).index(fx)
            return {
                "success": True,
                "fx_index": fx_idx,
                "name": fx.name,
                "n_params": fx.n_params,
                "track_index": track_index,
            }
        except Exception as e:
            logger.error(f"add_fx failed: {e}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def remove_fx(track_index: int, fx_index: int) -> dict:
        """Remove an FX plugin from a track by its index."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            fx_name = track.fxs[fx_index].name
            RPR.TrackFX_Delete(track.id, fx_index)
            return {"success": True, "track_index": track_index, "removed": fx_name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_fx_parameter(
        track_index: int, fx_index: int, param_index: int, value: float
    ) -> dict:
        """
        Set a normalized parameter value (0.0–1.0) on an FX plugin.
        Use get_fx_parameters to discover available parameters and their indices.
        """
        try:
            project = get_project()
            track = project.tracks[track_index]
            RPR.TrackFX_SetParamNormalized(track.id, fx_index, param_index, value)
            # Read back via RPR to confirm
            result = RPR.TrackFX_GetParamNormalized(track.id, fx_index, param_index)
            name = RPR.TrackFX_GetParamName(track.id, fx_index, param_index, "", 2048)[4]
            return {
                "success": True,
                "track_index": track_index,
                "fx_index": fx_index,
                "param_index": param_index,
                "param_name": name,
                "value": result,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_fx_parameters(track_index: int, fx_index: int) -> dict:
        """Get all parameters for an FX plugin, including names, indices, and current values."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            n_params = RPR.TrackFX_GetNumParams(track.id, fx_index)
            fx_name = RPR.TrackFX_GetFXName(track.id, fx_index, "", 2048)[3]
            params = []
            for i in range(n_params):
                name = RPR.TrackFX_GetParamName(track.id, fx_index, i, "", 2048)[4]
                norm_val = RPR.TrackFX_GetParamNormalized(track.id, fx_index, i)
                # TrackFX_GetParam returns:
                #   (retval, track_id, fx_idx, param_idx, minvalOut, maxvalOut)
                # so the current value is [0] and min/max are [4] and [5].
                # The previous [:3] slice put the track pointer into min_val
                # and the fx index into max_val.
                param_result = RPR.TrackFX_GetParam(track.id, fx_index, i, 0, 0)
                raw_val = param_result[0]
                min_val = param_result[4]
                max_val = param_result[5]
                formatted = RPR.TrackFX_GetFormattedParamValue(track.id, fx_index, i, "", 2048)[4]
                params.append({
                    "index": i,
                    "name": name,
                    "value": raw_val,
                    "normalized_value": norm_val,
                    "formatted_value": formatted,
                    "range": [min_val, max_val],
                })
            return {
                "success": True,
                "track_index": track_index,
                "fx_index": fx_index,
                "fx_name": fx_name,
                "parameters": params,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def list_track_fx(track_index: int) -> dict:
        """List all FX plugins on a track."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            fx_list = []
            for i in range(track.n_fxs):
                fx = track.fxs[i]
                fx_list.append({
                    "index": i,
                    "name": fx.name,
                    "enabled": fx.is_enabled,
                    "n_params": fx.n_params,
                })
            return {"success": True, "track_index": track_index, "fx": fx_list}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def bypass_fx(track_index: int, fx_index: int, bypassed: bool) -> dict:
        """Enable or bypass (disable) an FX plugin on a track."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            fx = track.fxs[fx_index]
            fx.is_enabled = not bypassed
            return {
                "success": True,
                "track_index": track_index,
                "fx_index": fx_index,
                "fx_name": fx.name,
                "bypassed": bypassed,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def load_fx_preset(track_index: int, fx_index: int, preset_name: str) -> dict:
        """Load a saved preset by name for an FX plugin."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            fx = track.fxs[fx_index]
            # reapy's FX exposes `preset` (not `preset_name`) as the settable
            # attribute. `preset` accepts a preset name, a path to a
            # .vstpreset file, or an int preset index.
            fx.preset = preset_name
            return {
                "success": True,
                "track_index": track_index,
                "fx_index": fx_index,
                "fx_name": fx.name,
                "preset": fx.preset,
            }
        except Exception as e:
            logger.error(f"load_fx_preset failed: {e}")
            return {"success": False, "error": str(e)}
