"""B04 pure editor routes, using canonical payloads and saved-text authority.

Install the MeshGL64 bridge before importing this module. Folder I/O belongs
to B09; this adapter receives its inventory_text/source_inventory_text snapshots.
"""
from functools import wraps
import hashlib
import json
from pathlib import Path

from wavefinity_web_impl._entry import (
    checked_entry_payload, read_inventory_snapshot, validate_design_open_guard,
)
from wavefinity_web_impl._designs import _features, _layout
from wavefinity_web_impl._runtime import SERVER_INSTANCE


_identity = {"instance": SERVER_INSTANCE}


def configure_catalog_identity(*, instance: str, build: str) -> None:
    """B14 supplies the same worker/session identity exposed by local health."""
    if not isinstance(instance, str) or not instance or not isinstance(build, str) or not build:
        raise ValueError("Browser catalog identity requires an instance and build.")
    _identity.update(instance=instance, build=build)


def catalog_payload(payload=None):
    directory = Path(__file__).parent
    data = (directory / "catalog.json").read_bytes()
    manifest = json.loads((directory / "catalog_manifest.json").read_text(encoding="utf-8"))
    if hashlib.sha256(data).hexdigest() != manifest["sha256"]:
        raise ValueError("Browser catalog integrity check failed.")
    catalog = json.loads(data)
    catalog.update(_identity)
    catalog["build"] = _identity.get("build", manifest["source_sha256"])
    catalog["catalog_version"] = manifest["schema"]
    catalog["catalog_sha256"] = manifest["sha256"]
    return catalog


def validate_payload(payload):
    return validate_design_open_guard(payload, read_inventory=read_inventory_snapshot)


def entry_route(handler):
    @wraps(handler)
    def guarded(payload):
        request = checked_entry_payload(payload, read_inventory=read_inventory_snapshot)
        return handler(request)
    return guarded


ROUTES = {
    "/api/catalog": catalog_payload,
    "/api/design/validate": validate_payload,
    "/api/design/inventory-preview": entry_route(_layout.inventory_preview_payload),
    "/api/design/division-label-fit": entry_route(_layout.division_label_fit_payload),
    "/api/feature/default": entry_route(_features.default_feature_payload),
    "/api/feature/draft": entry_route(_features.draft_payload),
    "/api/feature/fit": entry_route(_features.feature_fit_payload),
    "/api/feature/apply": entry_route(_features.apply_feature_payload),
    "/api/feature/duplicate": entry_route(_features.duplicate_feature_payload),
    "/api/feature/delete": entry_route(_features.delete_feature_payload),
    "/api/layout/mode": entry_route(_features.mode_payload),
    "/api/layout/expand": entry_route(_layout.expand_layout_payload),
    "/api/pegboard/layouts": _layout.pegboard_layouts_payload,
}
