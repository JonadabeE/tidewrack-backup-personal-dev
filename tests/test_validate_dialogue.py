"""Conditional-choice authoring regressions; no Godot required."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from validate_dialogue import CANONICAL_FLAGS, DIALOGUE_DIR, ROOT, reachable, validate_file


class ConditionalChoiceTests(unittest.TestCase):
    def validate(self, choices):
        graph = {"start": {"choices": choices}}
        return self.validate_graph(graph)

    def validate_graph(self, graph):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dialogue.json"
            path.write_text(json.dumps(graph))
            return validate_file(path)

    def test_existing_dialogue_is_unchanged_and_valid(self):
        for path in DIALOGUE_DIR.glob("*.json"):
            with self.subTest(path=path.name):
                self.assertEqual(validate_file(path), ([], []))

    def test_legacy_choice_without_requirements(self):
        self.assertEqual(self.validate([{"text": "Leave", "next": None}]), ([], []))

    def test_conditional_choice_with_fallback(self):
        self.assertEqual(self.validate([
            {"text": "Ask", "next": None,
             "requires_flag": {"trusted_edith": True, "radioed_tom": False}},
            {"text": "Leave", "next": None},
        ]), ([], []))

    def test_empty_object_is_a_fallback(self):
        self.assertEqual(self.validate([
            {"text": "Leave", "next": None, "requires_flag": {}},
        ]), ([], []))

    def test_all_conditional_choices_are_rejected(self):
        errors, _ = self.validate([
            {"text": "Yes", "next": None, "requires_flag": {"trusted_edith": True}},
            {"text": "No", "next": None, "requires_flag": {"trusted_edith": False}},
        ])
        self.assertTrue(any("unconditional fallback" in error for error in errors))

    def test_non_object_requirements_are_rejected(self):
        for value in (None, [], "trusted_edith", True, 1):
            with self.subTest(value=value):
                errors, _ = self.validate([
                    {"text": "Ask", "next": None, "requires_flag": value},
                    {"text": "Leave", "next": None},
                ])
                self.assertTrue(any("must be an object" in error for error in errors))

    def test_empty_flag_names_are_rejected(self):
        for key in ("", " ", "\t"):
            with self.subTest(key=key):
                errors, _ = self.validate([
                    {"text": "Ask", "next": None, "requires_flag": {key: True}},
                    {"text": "Leave", "next": None},
                ])
                self.assertTrue(any("nonempty flag names" in error for error in errors))

    def test_invalid_requirement_does_not_count_as_fallback(self):
        errors, _ = self.validate([
            {"text": "Ask", "next": None, "requires_flag": []},
        ])
        self.assertTrue(any("unconditional fallback" in error for error in errors))

    def test_hidden_choice_targets_are_still_validated(self):
        errors, _ = self.validate([
            {"text": "Ask", "next": "missing", "requires_flag": {"trusted_edith": True}},
            {"text": "Leave", "next": None},
        ])
        self.assertTrue(any("missing node" in error for error in errors))

    def test_malformed_choice_reports_error_without_crashing(self):
        errors, _ = self.validate([None, {"text": "Leave", "next": None}])
        self.assertTrue(any("needs a 'text' field" in error for error in errors))

    def test_canonical_flags_match_narrative_bible(self):
        bible = (ROOT / "docs" / "narrative-bible.md").read_text()
        section = bible.split("## Story flags (canonical)", 1)[1].split("\n## ", 1)[0]
        documented = set(re.findall(r"^\|\s*`([^`]+)`\s*\|", section, re.MULTILINE))
        self.assertTrue(documented, "Canonical flag table must not be empty")
        self.assertEqual(CANONICAL_FLAGS, documented)

    def test_all_canonical_names_are_accepted_in_all_supported_locations(self):
        flags = dict.fromkeys(CANONICAL_FLAGS, True)
        self.assertEqual(self.validate_graph({"start": {
            "set_flag": flags,
            "choices": [
                {"text": "Ask", "next": None, "requires_flag": flags, "set_flag": flags},
                {"text": "Leave", "next": None},
            ],
        }}), ([], []))

    def test_unknown_prerequisite_reports_exact_location_and_name(self):
        for name in ("trusted_edth", "lamp_relit", "Trusted_edith", " trusted_edith "):
            with self.subTest(name=name):
                self.assertEqual(self.validate([
                    {"text": "Ask", "next": None, "requires_flag": {name: False}},
                    {"text": "Leave", "next": None},
                ]), ([
                    f"dialogue.json:start: choice #0 'requires_flag' uses unknown story flag '{name}' "
                    "(see docs/narrative-bible.md: Story flags (canonical))"
                ], []))

    def test_unknown_node_effect_reports_exact_location_and_name(self):
        self.assertEqual(self.validate_graph({"start": {
            "next": None, "set_flag": {"lamp_relit": True},
        }}), ([
            "dialogue.json:start: 'set_flag' uses unknown story flag 'lamp_relit' "
            "(see docs/narrative-bible.md: Story flags (canonical))"
        ], []))

    def test_unknown_choice_effect_reports_exact_location_and_name(self):
        self.assertEqual(self.validate([
            {"text": "Leave", "next": None, "set_flag": {"radioed_tim": True}},
        ]), ([
            "dialogue.json:start: choice #0 'set_flag' uses unknown story flag 'radioed_tim' "
            "(see docs/narrative-bible.md: Story flags (canonical))"
        ], []))

    def test_setting_unknown_flag_does_not_make_it_canonical(self):
        errors, warnings = self.validate_graph({"start": {
            "set_flag": {"invented": True},
            "choices": [
                {"text": "Ask", "next": None, "requires_flag": {"invented": True}},
                {"text": "Leave", "next": None},
            ],
        }})
        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 2)
        self.assertTrue(all("unknown story flag 'invented'" in error for error in errors))

    def test_malformed_set_flag_is_rejected_at_node_and_choice(self):
        for value, reason in ((None, "must be an object"), ([], "must be an object"),
                              ({"": True}, "needs nonempty flag names")):
            with self.subTest(value=value):
                self.assertEqual(self.validate_graph({"start": {
                    "next": None, "set_flag": value,
                }}), ([f"dialogue.json:start: 'set_flag' {reason}"], []))
                self.assertEqual(self.validate([
                    {"text": "Leave", "next": None, "set_flag": value},
                ]), ([f"dialogue.json:start: choice #0 'set_flag' {reason}"], []))

    def test_cli_returns_one_for_unknown_flag_without_unrelated_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            dialogue = root / "data" / "dialogue"
            dialogue.mkdir(parents=True)
            script = root / "tests" / "validate_dialogue.py"
            script.write_text((ROOT / "tests" / "validate_dialogue.py").read_text())
            (dialogue / "invalid.json").write_text(json.dumps({"start": {
                "next": None, "set_flag": {"lamp_relit": True},
            }}))
            result = subprocess.run([sys.executable, "-B", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, "")
            self.assertIn("invalid.json:start: 'set_flag' uses unknown story flag 'lamp_relit'", result.stdout)
            self.assertIn("1 error(s), 0 warning(s)", result.stdout)

    def test_broken_reachability_examples(self):
        for filename, node in (("self_unlock.json", "start"), ("incompatible_paths.json", "merge")):
            with self.subTest(filename=filename):
                path = ROOT / "tests" / "fixtures" / "dialogue" / filename
                errors, warnings = validate_file(path)
                self.assertEqual(errors, [
                    f"{filename}:{node}: choice #0 is unreachable under any feasible flag state from entry points ['start']"
                ])
                self.assertEqual(warnings, [
                    f"{filename}:blocked: unreachable from entry points ['start'] with feasible flag states"
                ])

    def test_unknown_entry_flag_is_allowed_but_fresh_state_defaults_false(self):
        graph = {"start": {"choices": [
            {"text": "Ask", "requires_flag": {"trusted_edith": True}, "next": "secret"},
            {"text": "Leave", "next": None},
        ]}, "secret": {"next": None}}
        self.assertIn("secret", reachable(graph, {"start"})[0])
        self.assertNotIn("secret", reachable(graph, {"start"}, initial_flags={})[0])
        graph["start"]["choices"][0]["requires_flag"]["trusted_edith"] = False
        self.assertIn("secret", reachable(graph, {"start"}, initial_flags={})[0])

    def test_requirements_constrain_unknown_state_downstream(self):
        graph = {
            "start": {"choices": [
                {"text": "Enter", "requires_flag": {"trusted_edith": True}, "next": "inside"},
                {"text": "Leave", "next": None},
            ]},
            "inside": {"choices": [
                {"text": "Contradiction", "requires_flag": {"trusted_edith": False}, "next": None},
                {"text": "Leave", "next": None},
            ]},
        }
        errors, warnings = self.validate_graph(graph)
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [
            "dialogue.json:inside: choice #0 is unreachable under any feasible flag state from entry points ['start']"
        ])

    def test_node_effect_overwrites_incoming_choice_effect_before_requirements(self):
        graph = {
            "start": {"choices": [{"text": "Enter", "set_flag": {"trusted_edith": False}, "next": "inside"}]},
            "inside": {"set_flag": {"trusted_edith": True}, "choices": [
                {"text": "Ask", "requires_flag": {"trusted_edith": True}, "next": None},
                {"text": "Leave", "next": None},
            ]},
        }
        self.assertEqual(self.validate_graph(graph), ([], []))

    def test_changed_flags_allow_revisiting_node_and_cycle_terminates(self):
        graph = {
            "start": {"set_flag": {"trusted_edith": False}, "next": "loop"},
            "loop": {"choices": [
                {"text": "Unlock", "set_flag": {"trusted_edith": True}, "next": "loop"},
                {"text": "Exit", "requires_flag": {"trusted_edith": True}, "next": "end"},
            ]},
            "end": {"next": None},
        }
        self.assertEqual(self.validate_graph(graph), ([], []))

    def test_unreachable_choice_detected_even_when_target_is_reachable(self):
        errors, warnings = self.validate_graph({
            "start": {"set_flag": {"trusted_edith": False}, "choices": [
                {"text": "Blocked", "requires_flag": {"trusted_edith": True}, "next": "end"},
                {"text": "Leave", "next": "end"},
            ]}, "end": {"next": None},
        })
        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("choice #0 is unreachable", errors[0])

    def test_only_unreachable_terminal_is_not_enough(self):
        errors, warnings = self.validate_graph({
            "start": {"next": "start"}, "orphan": {"next": None},
        })
        self.assertEqual(errors, [
            "dialogue.json: no terminal reachable from entry points ['start'] with feasible flag states"
        ])
        self.assertEqual(len(warnings), 1)

    def test_non_boolean_values_and_types_are_preserved(self):
        graph = {"start": {"set_flag": {"trusted_edith": 1}, "choices": [
            {"text": "Boolean", "requires_flag": {"trusted_edith": True}, "next": None},
            {"text": "Numeric", "requires_flag": {"trusted_edith": 1.0}, "next": None},
            {"text": "Leave", "next": None},
        ]}}
        self.assertEqual(reachable(graph, {"start"})[1], {("start", 1), ("start", 2)})


if __name__ == "__main__":
    unittest.main()
