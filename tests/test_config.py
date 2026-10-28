import json
import tempfile
import unittest
from pathlib import Path

from cybermint_hud.config import DEFAULT_CONFIG, load_config, validate_config


class ConfigTests(unittest.TestCase):
    def test_defaults_are_independent_and_valid(self):
        one = validate_config(DEFAULT_CONFIG)
        one["positions"]["clock"]["x"] = 99
        two = validate_config(DEFAULT_CONFIG)
        self.assertEqual(two["positions"]["clock"]["x"], 32)
        self.assertEqual(two["appearance"]["scale"], 1.0)
        self.assertEqual(two["appearance"]["accent_primary"], "#ff2a4b")
        self.assertEqual(two["appearance"]["accent_secondary"], "#00f0ff")

    def test_custom_values_and_backward_compatibility(self):
        config = validate_config({
            "version": 1,
            "appearance": {
                "accent": "#FF3366",        # mapped to accent_primary
                "cyan": "#00E5FF",          # mapped to accent_secondary
                "opacity": 0.85,
                "scale": 1.25,
            },
            "positions": {
                "clock": {"x": 10, "y": 20},
                "system": {"x": 40, "y": 200},
            },
            "behavior": {
                "refresh_interval_seconds": 3,
                "always_on_top": False,
            },
        })
        self.assertEqual(config["appearance"]["accent_primary"], "#ff3366")
        self.assertEqual(config["appearance"]["accent_secondary"], "#00e5ff")
        self.assertEqual(config["appearance"]["opacity"], 0.85)
        self.assertEqual(config["appearance"]["scale"], 1.25)
        self.assertEqual(config["positions"]["clock"], {"x": 10, "y": 20})
        self.assertEqual(config["behavior"]["refresh_interval_seconds"], 3)
        self.assertFalse(config["behavior"]["always_on_top"])

    def test_invalid_values_are_rejected(self):
        invalid_cases = (
            {"version": 1, "appearance": {"accent_primary": "invalid_color"}, "positions": {}},
            {"version": 1, "appearance": {"opacity": 0.4}, "positions": {}},   # below min 0.65
            {"version": 1, "appearance": {"scale": 0.2}, "positions": {}},     # below min 0.75
            {"version": 1, "appearance": {"scale": 3.5}, "positions": {}},     # above max 2.5
            {"version": 1, "appearance": {}, "positions": {"clock": {"x": -5}}},
            {"version": 1, "appearance": {}, "positions": {}, "behavior": {"refresh_interval_seconds": 0}},
            {"version": 2, "appearance": {}, "positions": {}},                 # invalid version
        )
        for raw in invalid_cases:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_config(raw)

    def test_invalid_file_is_preserved_and_defaults_are_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt_config.json"
            original = "{\n  \"invalid\": json syntax...\n"
            path.write_text(original, encoding="utf-8")
            result = load_config(path)
            self.assertEqual(result, DEFAULT_CONFIG)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_new_file_is_created_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "subfolder" / "config.json"
            self.assertEqual(load_config(path), DEFAULT_CONFIG)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["version"], 1)
            self.assertIn("accent_primary", loaded["appearance"])
            self.assertIn("scale", loaded["appearance"])


if __name__ == "__main__":
    unittest.main()


class PositionTests(unittest.TestCase):
    def test_controls_position_has_default_and_is_validated(self):
        config = validate_config(DEFAULT_CONFIG)
        self.assertEqual(config["positions"]["controls"], {"x": 320, "y": 32})
        with self.assertRaises(ValueError):
            validate_config({"version": 1, "appearance": {}, "positions": {"controls": {"x": -5}}})

    def test_old_config_without_controls_still_loads(self):
        config = validate_config({"version": 1, "appearance": {}, "positions": {"clock": {"x": 1, "y": 2}}})
        self.assertEqual(config["positions"]["controls"], {"x": 320, "y": 32})

    def test_default_positions_scale_but_custom_positions_do_not(self):
        from cybermint_hud.config import effective_position

        config = validate_config({
            "version": 1,
            "appearance": {"scale": 1.5},
            "positions": {"clock": {"x": 20, "y": 20}},
        })
        self.assertEqual(effective_position(config, "clock"), {"x": 20, "y": 20})
        self.assertEqual(effective_position(config, "system"), {"x": 48, "y": 270})
        self.assertEqual(effective_position(validate_config(DEFAULT_CONFIG), "system"), {"x": 32, "y": 180})
