"""Conditional-choice authoring regressions; no Godot required."""
import json
from pathlib import Path
import tempfile
import unittest

from validate_dialogue import DIALOGUE_DIR, validate_file


class ConditionalChoiceTests(unittest.TestCase):
    def validate(self, choices):
        graph = {"start": {"choices": choices}}
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


if __name__ == "__main__":
    unittest.main()
