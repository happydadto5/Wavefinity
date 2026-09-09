"""Feature builder and default registries."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from typing import Callable

import trimesh

from organizer_engine import BoxSpec

from ._core import Feature


Builder = Callable[[BoxSpec, Feature, float], list[trimesh.Trimesh]]
Defaults = Callable[[BoxSpec, "Feature", float], dict[str, object]]
FEATURE_BUILDERS: dict[str, Builder] = {}
FEATURE_DEFAULTS: dict[str, Defaults] = {}


@dataclass(frozen=True)
class OptionDefinition:
    """Authoritative editor/serialization metadata for one feature option."""

    label: str
    key: str
    default: object = ""
    value_type: str = "number"
    editor: bool = True


@dataclass(frozen=True)
class FeatureDefinition:
    """One feature's builder, defaults, display data, and capabilities."""

    kind: str
    title: str
    display: str
    description: str
    capabilities: tuple[str, ...] = ()
    options: tuple[OptionDefinition, ...] = ()
    icon: str = ""
    order: int = 100
    builder: Builder | None = None
    default_resolver: Defaults | None = None

    @property
    def flags(self) -> dict[str, bool]:
        flags = {
            "qty": False, "size": False, "along": False,
            "item": False, "lean": False, "alternate": False,
            "photo": False, "text": False,
        }
        flags.update({name: True for name in self.capabilities})
        return flags


FEATURE_DEFINITIONS: dict[str, FeatureDefinition] = {}
OPTION_TYPES: dict[str, str] = {}


def _definition(kind: str) -> FeatureDefinition:
    return FEATURE_DEFINITIONS.get(kind, FeatureDefinition(
        kind=kind,
        title=kind.replace("_", " ").title(),
        display=kind.replace("_", " ").title(),
        description="",
    ))


def _register_option_types(options: tuple[OptionDefinition, ...]) -> None:
    for option in options:
        prior = OPTION_TYPES.get(option.key)
        if prior is not None and prior != option.value_type:
            raise ValueError(
                f"option {option.key!r} has conflicting types {prior!r} and "
                f"{option.value_type!r}"
            )
        OPTION_TYPES[option.key] = option.value_type


def feature(
    kind: str,
    *,
    title: str | None = None,
    display: str | None = None,
    description: str | None = None,
    capabilities: tuple[str, ...] | None = None,
    options: tuple[OptionDefinition, ...] | None = None,
    icon: str | None = None,
    order: int | None = None,
) -> Callable[[Builder], Builder]:
    def register(function: Builder) -> Builder:
        FEATURE_BUILDERS[kind] = function
        current = _definition(kind)
        chosen_options = current.options if options is None else tuple(options)
        _register_option_types(chosen_options)
        chosen_title = current.title if title is None else title
        FEATURE_DEFINITIONS[kind] = replace(
            current,
            title=chosen_title,
            display=(current.display if display is None else display) or chosen_title,
            description=current.description if description is None else description,
            capabilities=(current.capabilities if capabilities is None
                          else tuple(capabilities)),
            options=chosen_options,
            icon=(current.icon if icon is None and current.icon else
                  kind if icon is None and title is not None else icon or ""),
            order=current.order if order is None else order,
            builder=function,
        )
        return function
    return register


# A holder may leave an option unset, meaning "work it out from the bin, the
# zone or the stored item".  That was fine while only the builders needed the
# number, but the editor has to show it too: a parameter box that sits blank
# cannot be reasoned about or edited.  So each kind registers how it resolves
# its own defaults, once, and both the builder and the editor read them here.
@dataclass(frozen=True)
class SettingInteraction:
    """One discoverable automatic relationship between feature settings."""

    source: str
    target: str
    effect: str
    owner: str
    reason: str


SETTING_INTERACTIONS: dict[str, tuple[SettingInteraction, ...]] = {}


def register_setting_interactions(
    kind: str, rules: tuple[SettingInteraction, ...]
) -> None:
    """Register feature-local rules and reject automatic dependency loops."""
    automatic = {"auto-adjust", "derived"}
    graph: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for rule in rules:
        if not all((rule.source, rule.target, rule.effect, rule.owner, rule.reason)):
            raise ValueError("setting interactions need source, target, effect, owner, and reason")
    combined = {**SETTING_INTERACTIONS, kind: tuple(rules)}
    for registered in combined.values():
        for rule in registered:
            if rule.effect in automatic:
                graph.setdefault((rule.owner, rule.source), set()).add(
                    (rule.owner, rule.target)
                )

    visiting: set[tuple[str, str]] = set()
    visited: set[tuple[str, str]] = set()

    def visit(node: tuple[str, str]) -> None:
        if node in visiting:
            raise ValueError(
                f"automatic setting loop registered for {kind}: {node[0]}.{node[1]}"
            )
        if node in visited:
            return
        visiting.add(node)
        for target in graph.get(node, ()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for source in graph:
        visit(source)
    SETTING_INTERACTIONS[kind] = tuple(rules)


def setting_interactions(
    kind: str | None = None, target: str | None = None
) -> tuple[SettingInteraction, ...]:
    """Query the combined feature-local rules, optionally by kind and target."""
    rules = (SETTING_INTERACTIONS.get(kind, ()) if kind is not None else
             tuple(rule for group in SETTING_INTERACTIONS.values() for rule in group))
    if target is not None:
        rules = tuple(rule for rule in rules if rule.target == target)
    return tuple(rules)


def defaults(kind: str) -> Callable[[Defaults], Defaults]:
    def register(function: Defaults) -> Defaults:
        FEATURE_DEFAULTS[kind] = function
        FEATURE_DEFINITIONS[kind] = replace(
            _definition(kind), default_resolver=function
        )
        return function
    return register


def feature_definition(kind: str) -> FeatureDefinition:
    """Return one complete registered feature definition."""
    return FEATURE_DEFINITIONS[kind]


def feature_definitions() -> tuple[FeatureDefinition, ...]:
    """Return the authoritative palette in stable display order."""
    return tuple(sorted(
        FEATURE_DEFINITIONS.values(), key=lambda one: (one.order, one.kind)
    ))


def option_value(key: str, value: object, kind: str | None = None) -> object:
    """Coerce a saved/browser option according to registered metadata."""
    value_type = None
    if kind is not None and kind in FEATURE_DEFINITIONS:
        value_type = next((
            option.value_type
            for option in FEATURE_DEFINITIONS[kind].options
            if option.key == key
        ), None)
    value_type = value_type or OPTION_TYPES.get(key, "number")
    if value_type in {"string", "enum"}:
        return str(value)
    if value_type == "boolean":
        if isinstance(value, str):
            return value.strip().lower() not in {"", "false", "0", "no", "off"}
        return bool(value)
    if value_type == "integer":
        number = float(value)
        if not math.isfinite(number) or abs(number - round(number)) > 1e-9:
            raise ValueError(f"option {key!r} must be a whole number")
        return int(round(number))
    if value_type == "json":
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return [part.strip() for part in value.split(",") if part.strip()]
        return value
    return float(value)


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
