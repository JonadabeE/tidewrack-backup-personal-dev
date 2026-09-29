extends "res://scripts/game.gd"
class_name LampRoom
## Reuses the ground floor's player, proximity interaction, dialogue UI and pause
## menu. The lamp graph owns all narrative choices; stairs only change scenes.

const LAMP_DIALOGUE := "res://data/dialogue/keeper_lamp_room.json"


func _room_title() -> String:
	return "Cape Marrow Light — lamp room"


func _build_room() -> void:
	super._build_room()
	var lamp := ColorRect.new()
	lamp.color = Color("#2a2f33")
	lamp.size = Vector2(120, 120)
	lamp.position = Vector2(580, 220)
	add_child(lamp)


func _build_interactables() -> void:
	var lamp := _add_interactable("Great lamp", "Tend the great lamp", "start",
		Vector2(640, 280), Color("#8a6f4b"))
	lamp.dialogue_path = LAMP_DIALOGUE
	var stair := _add_interactable("Ground-floor stair", "Return to the radio and logbook", "",
		Vector2(640, 520), Color("#3a4a54"))
	stair.dialogue_path = ""
	stair.interacted.connect(_travel_to.bind("res://scenes/game.tscn"))


func is_lamp_lit() -> bool:
	# Existing scaffold hook; dialogue does not set this noncanonical flag.
	return bool(GameState.get_flag("lamp_relit", false))
