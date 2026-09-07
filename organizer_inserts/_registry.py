"""Feature builder and default registries."""

from __future__ import annotations

from typing import Callable

import trimesh

from organizer_engine import BoxSpec

from ._core import Feature


Builder = Callable[[BoxSpec, Feature, float], list[trimesh.Trimesh]]
FEATURE_BUILDERS: dict[str, Builder] = {}


def feature(kind: str) -> Callable[[Builder], Builder]:
    def register(function: Builder) -> Builder:
        FEATURE_BUILDERS[kind] = function
        return function
    return register


# A holder may leave an option unset, meaning "work it out from the bin, the
# zone or the stored item".  That was fine while only the builders needed the
# number, but the editor has to show it too: a parameter box that sits blank
# cannot be reasoned about or edited.  So each kind registers how it resolves
# its own defaults, once, and both the builder and the editor read them here.
Defaults = Callable[[BoxSpec, "Feature", float], dict[str, object]]
FEATURE_DEFAULTS: dict[str, Defaults] = {}


def defaults(kind: str) -> Callable[[Defaults], Defaults]:
    def register(function: Defaults) -> Defaults:
        FEATURE_DEFAULTS[kind] = function
        return function
    return register


def resolved_options(
    box: BoxSpec, spec_feature: "Feature", base_z: float = 0.0
) -> dict[str, object]:
    """Every option of a holder as a concrete number.

    Defaults first, then whatever the holder actually sets on top.  A default
    may read the options already chosen - a pocket's recess follows its height
    - so the two cascade the same way they did when each builder worked its
    own defaults out inline.
    """
    resolve = FEATURE_DEFAULTS.get(spec_feature.kind)
    resolved = dict(resolve(box, spec_feature, base_z)) if resolve else {}
    resolved.update({
        name: value for name, value in spec_feature.options.items()
        if value is not None
    })
    return resolved
