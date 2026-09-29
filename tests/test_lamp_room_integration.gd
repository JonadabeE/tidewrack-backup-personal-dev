extends SceneTree
## Headless scene traversal. Does not read or write the player's save file.

var _failures := 0


func _initialize() -> void:
	call_deferred("_run")


func _check(condition: bool, message: String) -> void:
	if not condition:
		_failures += 1
		printerr("FAIL: " + message)


func _settle() -> void:
	for i in 3:
		await process_frame


func _interact(scene: Node, label: String) -> void:
	var target: Node = null
	for item in scene._interactables:
		if item.label == label:
			target = item
	_check(target != null, "interaction exists: " + label)
	if target == null:
		return
	scene._player.position = target.position
	scene._process(0.0)
	_check(scene._nearest == target and scene._prompt.visible, "proximity prompt: " + label)
	var event := InputEventAction.new()
	event.action = "ui_accept"
	event.pressed = true
	scene._unhandled_input(event)
	await _settle()


func _run() -> void:
	var state: Node = root.get_node("GameState")
	var manager: Node = root.get_node("DialogueManager")
	change_scene_to_file("res://scenes/main_menu.tscn")
	await _settle()
	current_scene._on_new_game()
	await _settle()
	_check(current_scene.scene_file_path == "res://scenes/game.tscn", "New Game enters lighthouse")
	for trusted in [false, true]:
		for skeptic in [false, true]:
			state.set_flag("trusted_edith", trusted)
			state.set_flag("skeptic", skeptic)
			await _interact(current_scene, "Lamp-room stair")
			_check(current_scene.scene_file_path == "res://scenes/lamp_room.tscn", "stair enters lamp room")
			_check(state.current_scene == "res://scenes/lamp_room.tscn", "lamp room is current save scene")
			_check(not manager.is_active, "stair does not launch placeholder dialogue")
			await _interact(current_scene, "Great lamp")
			_check(manager.is_active and manager._current_id == "start", "lamp starts authored graph")
			_check(manager._graph.has("relight"), "authored graph loaded instead of placeholder")
			_check(not current_scene._player.can_move, "movement locked during dialogue")
			var visited: Array = []
			for step in 40:
				if not manager.is_active:
					break
				visited.append(manager._current_id)
				if manager._current_id in ["prepare", "response"]:
					_check(manager._visible_choices.size() == 1 + int(trusted) + int(skeptic), "conditional choices preserved")
				if manager._visible_choices.is_empty():
					manager.advance()
				else:
					# First visible path explores skeptic, trusted, or fallback branches.
					# At the ending, use share if present, otherwise stay with the lamp.
					var index: int = manager._visible_choices.size() - 1 if manager._current_id == "what_to_share" and not trusted else 0
					manager.choose(index)
				await process_frame
			_check(not manager.is_active, "lamp conversation ends")
			_check("relight" in visited and "answer" in visited, "relight and answer reached")
			_check(current_scene._player.can_move, "movement restored after dialogue")
			_check(state.flag_matches("trusted_edith", trusted) and state.flag_matches("skeptic", skeptic), "selected paths preserve flags")
			current_scene._toggle_pause()
			_check(current_scene._paused and not current_scene._player.can_move, "lamp room pause menu works")
			# Resume through the actual menu button.
			var buttons := current_scene.get_node("PauseLayer").find_children("*", "Button", true, false)
			buttons[0].pressed.emit()
			await process_frame
			var cancel := InputEventAction.new()
			cancel.action = "ui_cancel"
			cancel.pressed = true
			current_scene._unhandled_input(cancel)
			_check(current_scene.has_node("PauseLayer"), "Escape opens pause overlay")
			current_scene._unhandled_input(cancel)
			await process_frame
			_check(not current_scene.has_node("PauseLayer") and not current_scene._paused and current_scene._player.can_move, "Escape resumes and removes overlay")
			await _interact(current_scene, "Ground-floor stair")
			_check(current_scene.scene_file_path == "res://scenes/game.tscn", "return stair reaches lighthouse")
			_check(state.current_scene == "res://scenes/game.tscn", "return updates saved scene")
			await _interact(current_scene, "Radio set")
			_check(manager.is_active and manager._current_id == "radio", "radio still works after round trip")
			manager._finish()
			await process_frame
	print("Lamp-room integration failures: %d" % _failures)
	quit(0 if _failures == 0 else 1)
