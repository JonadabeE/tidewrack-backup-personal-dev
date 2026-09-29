extends SceneTree
## Run: godot --headless --path . --script tests/test_dialogue_manager.gd
## Uses in-memory state only; never reads or writes the player's save.

var _manager: Node
var _state: Node
var _shown: Array = []
var _finished: int = 0
var _failures: int = 0


func _initialize() -> void:
	call_deferred("_run")


func _check(condition: bool, message: String) -> void:
	if not condition:
		_failures += 1
		printerr("FAIL: " + message)


func _show(graph: Dictionary) -> void:
	_shown = []
	_manager._graph = graph
	_manager.is_active = true
	_manager._goto("start")


func _run() -> void:
	_manager = root.get_node("DialogueManager")
	_state = root.get_node("GameState")
	_manager.line_shown.connect(func(_speaker, _text, choices): _shown = choices)
	_manager.dialogue_finished.connect(func(): _finished += 1)
	_state.new_game()
	_check(_state.flag_matches("trusted_edith", false), "public check defaults absent flags to false")
	_check(not _state.flag_matches("trusted_edith", true), "public check rejects absent true flag")
	_check(not _state.flags.has("trusted_edith"), "public check does not insert absent flags")
	_state.set_flag("trusted_edith", true)
	_check(_state.flag_matches("trusted_edith", true), "public check matches stored true")
	_check(not _state.flag_matches("trusted_edith", false), "public check rejects mismatched value")
	_state.set_flag("trusted_edith", false)
	_check(_state.flag_matches("trusted_edith", false), "public check matches explicit false")
	_state.new_game()
	_check(_manager._meets_requirements({}), "empty requirements pass")
	_check(_manager._meets_requirements({"missing": false}), "absent flags default to false")
	_check(not _manager._meets_requirements({"missing": true}), "absent flags fail true requirements")
	_state.set_flag("trusted_edith", true)
	_check(not _manager._meets_requirements({"trusted_edith": true, "radioed_tom": true}), "all requirements must match")
	_state.set_flag("radioed_tom", true)
	_check(_manager._meets_requirements({"trusted_edith": true, "radioed_tom": true}), "multiple matching flags pass")
	_state.new_game()

	_show({"start": {"choices": [
		{"text": "Hidden", "next": null, "requires_flag": {"secret": true}, "set_flag": {"wrong": true}},
		{"text": "Visible", "next": "end", "set_flag": {"correct": true}}
	]}, "end": {"next": null}})
	_check(_shown.size() == 1 and _shown[0]["text"] == "Visible", "hidden first choice is filtered")
	_manager.advance()
	_check(_manager._current_id == "start", "advance waits for visible choices")
	_manager.choose(-1)
	_manager.choose(1)
	_check(not _state.get_flag("correct"), "invalid indices have no effects")
	_state.set_flag("secret", true)
	_manager.choose(0)
	_check(_state.get_flag("correct") and not _state.get_flag("wrong"), "displayed index remains stable after flag changes")
	_check(_manager._current_id == "end" and _manager._visible_choices.is_empty(), "transition clears visible choices")
	_manager.advance()
	_check(not _manager.is_active, "linear ending still works")

	_show({"start": {"set_flag": {"entered": true}, "choices": [
		{"text": "Unlocked", "next": null, "requires_flag": {"entered": true}},
		{"text": "Leave", "next": null, "requires_flag": {}}
	]}})
	_check(_shown.size() == 2, "node effects run before filtering; empty requirements stay visible")
	_manager.choose(0)
	_check(not _manager.is_active and _manager._visible_choices.is_empty(), "terminal choice clears state")

	var before: int = _finished
	print("Expect one no-visible-choices error for the deliberate invalid graph:")
	_show({"start": {"set_flag": {"entry_effect": true}, "choices": [
		{"text": "Hidden", "next": null, "requires_flag": {"never_set": true}}
	]}})
	_check(not _manager.is_active and _finished == before + 1, "zero choices finishes dialogue")
	_check(_shown.is_empty() and _manager._visible_choices.is_empty(), "zero choices emits no unusable line")
	_check(_state.get_flag("entry_effect"), "node-entry effects are retained")

	_state.new_game()
	_check(_manager.start("res://data/dialogue/keeper_intro.json", "logbook"), "legacy graph loads")
	_manager.advance()
	_manager.advance()
	_check(_shown.size() == 2, "legacy choices remain available")
	_manager.choose(0)
	_check(_state.get_flag("skeptic"), "legacy choice effects still run")
	_manager._finish()
	print("DialogueManager regression failures: %d" % _failures)
	quit(0 if _failures == 0 else 1)
