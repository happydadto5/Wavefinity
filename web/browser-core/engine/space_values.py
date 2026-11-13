"""Pure value operations for B09's JavaScript routes; no files or preferences.

This is an internal worker channel, not a Python API route registry. Browser
handles and all persistent writes remain in space-store.js/preferences.js.
"""
import json
import math

from organizer_inventory import parse_inventory, render_inventory
from organizer_inventory._space import configure_space_text, normalise_space_definition
from organizer_inventory._rows import _duplicate_name, verify_space_bins, owned_design_grid
from organizer_outputs.printer_profile import (
    apply_printer_profile_to_preferences, default_printer_profile_state,
    printer_profile_state, PRINTER_PREF_KEYS,
)


def compute(operation, payload):
    if not isinstance(payload, dict):
        raise ValueError("Space operation needs an object.")
    if operation in {"create-text", "configure-text", "update-text"}:
        return configure_space_text(
            str(payload.get("inventory_text") or ""),
            title=str(payload.get("inventory_title") or payload.get("name") or "Wavefinity"),
            raw_def=payload,
            mode="create" if operation == "create-text" else "update",
            allow_legacy=operation == "configure-text",
        )
    if operation == "copy-name":
        names = payload.get("names") or []
        if not isinstance(names, list):
            raise ValueError("Space names must be a list.")
        source = str(payload.get("name") or "").strip()
        return {"name": _duplicate_name([{"name": n} for n in [*names, source]], source)}
    if operation == "copy-text":
        current = parse_inventory(str(payload.get("inventory_text") or ""))
        space = verify_space_bins(current, payload.get("space"))
        resume = payload.get("resume_design")
        if isinstance(resume, dict):
            owned_design_grid(resume, space)
        name = str(payload.get("name") or "").strip()
        if not name or len(name) > 80:
            raise ValueError("Give the copied Space a name of at most 80 characters.")
        current["layout"]["space"] = {**space, "name": name}
        return {"inventory_text": render_inventory(name, current["bins"], current["layout"])}
    if operation == "validate":
        return {"space": normalise_space_definition(payload["space"])}
    if operation == "printer-profile":
        prefs = dict(payload.get("preferences") or {})
        if payload.get("reset") is True:
            for key in PRINTER_PREF_KEYS:
                prefs.pop(key, None)
            prefs.pop("printer_profile_malformed", None)
        elif payload.get("profile") is not None:
            prefs = apply_printer_profile_to_preferences(prefs, payload["profile"])
            prefs.pop("printer_profile_malformed", None)
        try:
            state = printer_profile_state(prefs)
        except ValueError:
            state = default_printer_profile_state(
                "Printer Settings could not be read. Choose Reset Printer Settings to use the defaults.")
        if prefs.get("printer_profile_malformed"):
            state["malformed"] = prefs["printer_profile_malformed"]
        return {**state, "preferences": prefs}
    if operation == "preferences":
        from organizer_base_trim import BASE_TRIM_BED_EDGE_MARGIN
        from organizer_engine import connector_arm_thickness_floor
        update = {}
        for key in ("base_trim_bed_x_mm", "base_trim_bed_y_mm"):
            if key in payload:
                value = float(payload[key])
                if not math.isfinite(value) or value <= 2 * BASE_TRIM_BED_EDGE_MARGIN:
                    raise ValueError("Bed size must leave a positive printable area after edge clearance.")
                update[key] = value
        if "connector_settings" in payload:
            raw = payload["connector_settings"]
            if not isinstance(raw, dict):
                raise ValueError("Connector settings must be an object.")
            settings = {}
            for key, low, high in (("tolerance", 0, 1), ("length", 2, None),
                                   ("arm_thickness", .5, 10), ("bin_a_height", 2, None),
                                   ("bin_b_height", 2, None)):
                value = raw.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("Connector settings must be numbers.")
                if not math.isfinite(value) or value < low or (high is not None and value > high):
                    raise ValueError("Connector settings are outside the allowed range.")
                if key == "arm_thickness" and value <= connector_arm_thickness_floor():
                    raise ValueError("Connector arm thickness is too thin to generate.")
                settings[key] = value
            if not isinstance(raw.get("different_heights"), bool):
                raise ValueError("Connector settings are incomplete.")
            settings["different_heights"] = raw["different_heights"]
            update["connector_settings"] = settings
        return update
    raise ValueError("Unknown local Space value operation.")


def compute_json(operation, payload_json):
    try:
        return json.dumps({"result": compute(operation, json.loads(payload_json))}, allow_nan=False)
    except (ValueError, TypeError, KeyError) as error:
        return json.dumps({"error": {"message": str(error), "kind": type(error).__name__}, "status": 400})
