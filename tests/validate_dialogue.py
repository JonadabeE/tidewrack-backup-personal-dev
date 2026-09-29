#!/usr/bin/env python3
"""Validate Tidewrack dialogue graphs without needing the Godot engine.

Checks, for every data/dialogue/*.json file:
  - it parses as a JSON object of node_id -> node
  - each node is either a linear node ("next": id|null) or a choice node
    ("choices": [{text, next, set_flag?, requires_flag?}]) — not neither, not both
  - choice requires_flag and node/choice set_flag are objects using canonical
    story flag names from docs/narrative-bible.md
  - each choice node has an unconditional fallback (no requirements or {})
  - every referenced target id exists
  - prerequisites and flag effects determine feasible nodes and choices
  - at least one terminal (next == null) is reachable from known entries
  - reports orphan nodes (unreachable from any known entry) as warnings

Exit code 0 = all valid, 1 = at least one error.

Usage:  python3 tests/validate_dialogue.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Entry-point node ids the game starts graphs from (see scripts/game.gd).
KNOWN_ENTRIES = {"logbook", "radio", "door", "start"}

# docs/narrative-bible.md, "Story flags (canonical)" is authoritative.
# Update both together when introducing story flags; a regression checks parity.
CANONICAL_FLAGS = frozenset({"skeptic", "believer", "trusted_edith", "radioed_tom"})

ROOT = Path(__file__).resolve().parent.parent
DIALOGUE_DIR = ROOT / "data" / "dialogue"


def validate_flags(value: object, field: str, location: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{location} '{field}' must be an object"]
    errors = []
    for name in value:
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{location} '{field}' needs nonempty flag names")
        elif name not in CANONICAL_FLAGS:
            errors.append(
                f"{location} '{field}' uses unknown story flag '{name}' "
                "(see docs/narrative-bible.md: Story flags (canonical))"
            )
    return errors


def same_value(left: object, right: object) -> bool:
    """JSON value equality without Python's bool == int coercion."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_value(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_value(a, b) for a, b in zip(left, right))
    return left == right


def reachable(graph: dict, entries: set[str], initial_flags: dict | None = None
              ) -> tuple[set[str], set[tuple[str, int]], bool]:
    """Explore feasible (node, flag constraints) states, not just graph edges.

    None means arbitrary carried-in flags. A supplied dict is a concrete entry
    state, with absent flags defaulting to false, just like GameState.get_flag().
    Independent path dictionaries preserve correlations between requirements.
    Only constant assignments and equality tests exist, so cycles reach a finite
    fixed point. A node may be revisited with different flag constraints.
    """
    initial = {} if initial_flags is None else {
        name: initial_flags.get(name, False) for name in CANONICAL_FLAGS
    }
    stack = [(entry, initial.copy()) for entry in sorted(entries) if entry in graph]
    visited: set[tuple[str, str]] = set()
    nodes: set[str] = set()
    choices: set[tuple[str, int]] = set()
    terminal = False
    while stack:
        nid, state = stack.pop()
        node = graph[nid]
        state = {**state, **node.get("set_flag", {})}
        key = (nid, json.dumps(state, sort_keys=True))
        if key in visited:
            continue
        visited.add(key)
        nodes.add(nid)
        options = node.get("choices", [])
        if options:
            for index, choice in enumerate(options):
                requirements = choice.get("requires_flag", {})
                if any(name in state and not same_value(state[name], value)
                       for name, value in requirements.items()):
                    continue
                choices.add((nid, index))
                # Unknown incoming flags are constrained by taking this choice.
                # Effects happen only after its requirements have been met.
                next_state = {**state, **requirements, **choice.get("set_flag", {})}
                target = choice.get("next")
                if target is None:
                    terminal = True
                else:
                    stack.append((target, next_state))
        else:
            target = node.get("next")
            if target is None:
                terminal = True
            else:
                stack.append((target, state))
    return nodes, choices, terminal


def validate_file(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        graph = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON — {exc}"], warnings

    if not isinstance(graph, dict):
        return [f"{path.name}: top level must be an object of node_id -> node"], warnings

    has_terminal = False
    for nid, node in graph.items():
        if not isinstance(node, dict):
            errors.append(f"{path.name}:{nid}: node must be an object")
            continue

        errors += validate_flags(node.get("set_flag", {}), "set_flag", f"{path.name}:{nid}:")

        has_choices = isinstance(node.get("choices"), list) and len(node["choices"]) > 0
        has_next = "next" in node
        if "choices" in node and not isinstance(node["choices"], list):
            errors.append(f"{path.name}:{nid}: 'choices' must be an array")

        if not has_choices and not has_next:
            errors.append(f"{path.name}:{nid}: node has neither 'next' nor 'choices'")
        if has_choices and has_next:
            errors.append(f"{path.name}:{nid}: node has both 'next' and 'choices' (ambiguous)")

        if has_next and node.get("next") is None:
            has_terminal = True

        if has_next and node["next"] is not None and not isinstance(node["next"], str):
            errors.append(f"{path.name}:{nid}: 'next' must be a node id or null")

        if has_next and isinstance(node.get("next"), str) and node["next"] not in graph:
            errors.append(f"{path.name}:{nid}: 'next' points to missing node '{node['next']}'")

        if has_choices:
            has_fallback = False
            for i, choice in enumerate(node["choices"]):
                if not isinstance(choice, dict) or "text" not in choice:
                    errors.append(f"{path.name}:{nid}: choice #{i} needs a 'text' field")
                    continue
                requirements = choice.get("requires_flag", {})
                location = f"{path.name}:{nid}: choice #{i}"
                errors += validate_flags(requirements, "requires_flag", location)
                errors += validate_flags(choice.get("set_flag", {}), "set_flag", location)
                if isinstance(requirements, dict) and not requirements:
                    has_fallback = True
                target = choice.get("next")
                if target is not None and (not isinstance(target, str) or target not in graph):
                    errors.append(f"{path.name}:{nid}: choice #{i} 'next' -> missing node '{target}'")
                if target is None:
                    has_terminal = True
            if not has_fallback:
                errors.append(f"{path.name}:{nid}: choice node needs an unconditional fallback (omit 'requires_flag' or use {{}})")

    if not has_terminal:
        errors.append(f"{path.name}: no terminal node (a node with next == null) — the graph never ends")

    entries = KNOWN_ENTRIES & set(graph.keys())
    if not entries:
        warnings.append(f"{path.name}: no known entry point ({sorted(KNOWN_ENTRIES)}) present")
    elif not errors:
        # Do not analyze invalid shapes or unknown flags, or emit misleading
        # reachability diagnostics for a graph that failed structural checks.
        seen, selectable, terminal = reachable(graph, entries)
        for orphan in sorted(set(graph) - seen):
            warnings.append(f"{path.name}:{orphan}: unreachable from entry points {sorted(entries)} with feasible flag states")
        for nid, node in graph.items():
            for index, _choice in enumerate(node.get("choices", [])):
                if (nid, index) not in selectable:
                    errors.append(f"{path.name}:{nid}: choice #{index} is unreachable under any feasible flag state from entry points {sorted(entries)}")
        if not terminal:
            errors.append(f"{path.name}: no terminal reachable from entry points {sorted(entries)} with feasible flag states")

    return errors, warnings


def main() -> int:
    files = sorted(DIALOGUE_DIR.glob("*.json"))
    if not files:
        print(f"No dialogue files found in {DIALOGUE_DIR}")
        return 1

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for path in files:
        errs, warns = validate_file(path)
        all_errors += errs
        all_warnings += warns
        status = "OK" if not errs else "FAIL"
        print(f"[{status}] {path.relative_to(ROOT)}  ({len(json.loads(path.read_text()))} nodes)")

    for w in all_warnings:
        print(f"  warning: {w}")
    for e in all_errors:
        print(f"  ERROR:   {e}")

    print()
    if all_errors:
        print(f"✗ {len(all_errors)} error(s), {len(all_warnings)} warning(s)")
        return 1
    print(f"✓ all dialogue graphs valid ({len(all_warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# --- Public Demo: journal graphs -------------------------------------------
# The journal system (scripts/journal.gd) reads discovered-log entries from the
# same JSON-graph format, so they validate through the checker above. Journal
# graphs live under data/dialogue/ with an "entry_*" id and are held to the same
# rules (targets resolve, a terminal exists). This hook is a placeholder until
# the journal content lands for the public demo.
JOURNAL_ENTRY_PREFIX = "entry_"


def is_journal_graph(graph: dict) -> bool:
	return any(str(k).startswith(JOURNAL_ENTRY_PREFIX) for k in graph)
