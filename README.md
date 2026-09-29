# Tidewrack

A narrative adventure set on a fog-bound island off the Washington coast. You
are the new keeper of **Cape Marrow Light**. The keeper before you, Edith Vane,
rowed out into the fog eleven days ago and did not come back.

Built solo by **Fogline Games** (Seattle) in **Godot 4**, shipping to Steam.

> **Status:** Public-demo candidate (Steam Next Fest). Vertical slice +
> branching conversation with save/load. See [`docs/milestones.md`](docs/milestones.md)
> for the road to launch.

## Controls

| Action        | Key                     |
|---------------|-------------------------|
| Move          | Arrow keys              |
| Interact      | Enter / Space           |
| Advance / skip line | Enter / Space     |
| Pause / back  | Esc                     |

The game uses only Godot's built-in input actions, so it works with no input
remapping (controller support and remappable keys are a Public Demo milestone).

## Running it

Requires **Godot 4.3+** (standard, non-.NET build).

```bash
# Open in the editor
godot -e --path .

# Or run directly
godot --path .
```

The main scene is `scenes/main_menu.tscn`. Saves are written to Godot's
`user://save.json` (per-OS user data dir).

## Project layout

```
tidewrack/
├── project.godot            # engine config; registers the two autoloads
├── scenes/                  # thin .tscn wrappers (root node + script)
│   ├── main_menu.tscn
│   ├── game.tscn            # the vertical-slice level
│   └── ui/{dialogue_box,settings}.tscn
├── scripts/
│   ├── autoload/
│   │   ├── game_state.gd     # story flags + save/load  (autoload: GameState)
│   │   └── dialogue_manager.gd  # branching graph player (autoload: DialogueManager)
│   ├── main_menu.gd, settings.gd
│   ├── game.gd               # builds the level + HUD + pause menu
│   ├── player.gd             # top-down movement (Player)
│   ├── interactable.gd       # examinable world object (Interactable)
│   └── dialogue_box.gd       # dialogue UI, listens to DialogueManager
├── data/dialogue/
│   └── keeper_intro.json     # the keeper's-log conversation
├── assets/{sprites,audio,fonts}/   # placeholder art for now
├── tests/validate_dialogue.py      # engine-free dialogue-graph checker
└── docs/                     # GDD, narrative bible, milestones, credits
```

**Design note:** UI and levels are constructed in GDScript rather than authored
as large scene files. This keeps `.tscn` files small and reviewable in diffs and
avoids merge pain — a deliberate choice for a one-person studio.

## The dialogue system

Conversations are plain JSON graphs in `data/dialogue/`. Each node is either a
linear line (`"next": "<id>"`, or `null` to end) or a choice node (`"choices"`).
Any node can set story flags via `"set_flag"`, which `GameState` persists.

```json
{
  "start": { "speaker": "Edith", "text": "…", "next": "choice1" },
  "choice1": {
    "text": "…",
    "choices": [
      { "text": "Trust her", "next": "end", "set_flag": { "trusted_edith": true } }
    ]
  },
  "end": { "speaker": "", "text": "…", "next": null }
}
```

Choices can optionally require existing flags using `requires_flag`, with the
same object style as `set_flag`:

```json
{
  "text": "Ask him about Edith.",
  "requires_flag": { "trusted_edith": true },
  "next": "radio_edith",
  "set_flag": { "radioed_tom": true }
}
```

This is a schema example; existing conversations remain unchanged. All listed
requirements are checked by the read-only public method
`GameState.flag_matches(name, expected)`, which compares `get_flag(name)` with
the expected value. Missing flags default to
`false`, so requiring `false` also matches a flag that has never been set.
Omitting `requires_flag` or using `{}` makes a choice unconditional.

Node `set_flag` effects run first, then available choices are captured for that
line. The UI and `choose(index)` use that same filtered list; availability stays
fixed until the next node. Choice effects still run only when selected.
Every choice node must include at least one unconditional fallback, even if its
conditions appear exhaustive. If an invalid graph has no visible choices at
runtime, the manager reports the node ID and ends dialogue, restoring movement;
node-entry effects are not rolled back.

The save format and flag names are unchanged. The validator checks requirement
shape, fallback availability, and flag names in choice `requires_flag` and
node/choice `set_flag` objects. Only the canonical flags in
[`docs/narrative-bible.md`](docs/narrative-bible.md#story-flags-canonical) are
allowed: `skeptic`, `believer`, `trusted_edith`, and `radioed_tom`. Names are
case-sensitive and are not trimmed. Add new story flags to the narrative bible
and the validator's `CANONICAL_FLAGS` together; a regression checks they agree.
The scaffold's `lamp_relit` is not canonical yet and is rejected in dialogue.
This check does not restrict flag values or modify saved flags.

Reachability tracks separate `(node, flag state)` paths. Node effects run before
requirements; choice effects run after them. A node can be revisited with changed
flags, while repeated states stop cycles. Impossible choices are errors, even if
another choice reaches the same target; unreachable nodes remain warnings. An
ending must be reachable, not merely present. This does not prove that every
branch or state can reach an ending.

Entry flags are unknown by default: conversations can inherit flags from saves
or earlier interactions. Requirements constrain those unknowns along each path;
assignments overwrite them. This conservatively proves local impossibility,
not whether a carried-in state is achievable across the whole game. The Python
`reachable(..., initial_flags={})` helper can also check a fresh-game state,
where missing flags are false. No entry-state fields are added to dialogue JSON.
Broken reachability examples live in `tests/fixtures/dialogue/`, outside the
normal content scan.

## Verifying changes

The lamp-room chapter is authored in `data/dialogue/keeper_lamp_room.json`,
starting at `start`: tend and relight the lamp, observe the answering light, then
decide what to share. `trusted_edith` gates recording/sharing choices; `skeptic`
gates reflection checks and a signal test. Every choice node has an unconditional
option. Keeping the account private sets `trusted_edith` to false; the other
paths preserve existing flags. Planning to speak to Tom does not set
`radioed_tom`, since no radio conversation occurs here.

The scene remains a scaffold: this graph is not yet wired to the lamp interaction.
The old `lamp_room.json` placeholder remains, and no `lamp_relit` state is written.

```bash
# Validate every dialogue graph (targets resolve, has an ending, no orphans)
python3 tests/validate_dialogue.py

# Conditional-choice validator regressions
python3 -m unittest discover -s tests -p 'test_*.py'

# Runtime regressions (in-memory flags; does not touch save.json)
godot --headless --path . --script tests/test_dialogue_manager.gd

# In-engine checks (requires Godot on PATH)
godot --headless --path . --check-only   # parse all scripts
```

> The GDScript in this build was authored without a local Godot install, so it
> has been checked statically and via the dialogue validator, **not** yet run in
> the engine. First engine open may surface minor fixups — tracked in the issue
> list.

## Steam Next Fest demo

The public demo (target: **Steam Next Fest**) extends the vertical slice with
the lamp-room chapter, a discovered-logs journal, and controller support. Demo
scope is locked in [`docs/milestones.md`](docs/milestones.md); the build is
feature-frozen and tagged `v0.2-demo-rc`.

Demo controls add a gamepad (analog stick + A/B) on top of the keyboard bindings.
