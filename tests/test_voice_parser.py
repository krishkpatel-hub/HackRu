import unittest

from companion.voice.parser import parse_command


class ParserTests(unittest.TestCase):
    def test_supported_phrases(self):
        commands = {
            "create cube": {"action": "spawn", "shape": "cube"},
            "add cube": {"action": "spawn", "shape": "cube"},
            "create sphere": {"action": "spawn", "shape": "sphere"},
            "add sphere": {"action": "spawn", "shape": "sphere"},
            "create cylinder": {"action": "spawn", "shape": "cylinder"},
            "add cylinder": {"action": "spawn", "shape": "cylinder"},
            "create triangular prism": {"action": "spawn", "shape": "prism"},
            "create prism": {"action": "spawn", "shape": "prism"},
            "add prism": {"action": "spawn", "shape": "prism"},
            "add triangular prism": {"action": "spawn", "shape": "prism"},
            "rotate": {"action": "set_mode", "mode": "ROTATE", "axis": "Z"},
            "rotate x": {"action": "set_mode", "mode": "ROTATE", "axis": "X"},
            "rotate y": {"action": "set_mode", "mode": "ROTATE", "axis": "Y"},
            "rotate z": {"action": "set_mode", "mode": "ROTATE", "axis": "Z"},
            "scale": {"action": "set_mode", "mode": "SCALE"},
            "extrude": {"action": "set_mode", "mode": "EXTRUDE"},
            "move": {"action": "set_mode", "mode": "MOVE"},
            "cancel": {"action": "cancel"},
            "undo": {"action": "undo"},
        }
        for text, expected in commands.items():
            for variant in [text, text.upper(), f"  {text.title()}!!!  "]:
                with self.subTest(text=variant):
                    self.assertEqual(parse_command(variant), expected)

    def test_punctuation_and_whitespace(self):
        self.assertEqual(parse_command('“Create,\ttriangular-prism.”'),
                         {"action": "spawn", "shape": "prism"})
        self.assertEqual(parse_command("Rotate: X?"),
                         {"action": "set_mode", "mode": "ROTATE", "axis": "X"})

    def test_rejects_conversation_and_unsupported_commands(self):
        for text in ["", "...", "cube", "sphere", "I like cubes", "create cube please",
                     "please create cube", "don't create cube", "we should add cube later",
                     "create cube and sphere", "create cube undo", "rotate around x",
                     "rotate 90", "rotate q", "move that", "add cone", "createcube",
                     "undo undo", "scale 2", "cancel subscription", "create 🧊 cube"]:
            with self.subTest(text=text):
                self.assertIsNone(parse_command(text))

    def test_results_are_fresh_and_have_no_id(self):
        first = parse_command("create cube")
        first["id"] = "changed"
        self.assertEqual(parse_command("create cube"), {"action": "spawn", "shape": "cube"})
