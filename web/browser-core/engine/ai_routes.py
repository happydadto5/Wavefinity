"""B13 canonical local AI routes. B14 assembles this map in Python only."""
from wavefinity_web_impl import _ai
from wavefinity_web_impl._ai import ai_repair_prompt_payload
from wavefinity_web_impl._entry import read_inventory_snapshot
from .editor_routes import catalog_payload
from .preview_routes import preview_payload


def ai_prompt_payload(payload):
    return _ai.ai_prompt_payload(payload, read_inventory=read_inventory_snapshot,
                                 catalog_payload=catalog_payload)


def ai_candidate_payload(payload):
    return _ai.ai_candidate_payload(payload, read_inventory=read_inventory_snapshot,
                                    preview_payload=preview_payload)


ROUTES = {
    '/api/ai/prompt': ai_prompt_payload,
    '/api/ai/candidate': ai_candidate_payload,
    '/api/ai/repair-prompt': ai_repair_prompt_payload,
}
