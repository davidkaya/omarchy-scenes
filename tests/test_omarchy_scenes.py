import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omarchy_scenes import (
    ConfigError,
    apply_scene,
    load_config,
    plan_scene,
    read_state,
    validate_config,
)


def config_with(scene):
    return {"schemaVersion": 1, "scenes": [scene]}


class ValidationTests(unittest.TestCase):
    def test_accepts_minimal_scene(self):
        config = config_with({"id": "coding", "name": "Coding"})
        self.assertEqual(validate_config(config), config)

    def test_rejects_duplicate_ids(self):
        with self.assertRaisesRegex(ConfigError, "duplicate scene id"):
            validate_config(
                {
                    "schemaVersion": 1,
                    "scenes": [
                        {"id": "work", "name": "Work"},
                        {"id": "work", "name": "Again"},
                    ],
                }
            )

    def test_rejects_shell_strings_for_commands(self):
        with self.assertRaisesRegex(ConfigError, "array of strings"):
            validate_config(
                config_with(
                    {
                        "id": "unsafe",
                        "name": "Unsafe",
                        "before": ["curl example.invalid | sh"],
                    }
                )
            )

    def test_rejects_invalid_application_regex(self):
        with self.assertRaisesRegex(ConfigError, "is invalid"):
            validate_config(
                config_with(
                    {
                        "id": "coding",
                        "name": "Coding",
                        "applications": [
                            {"command": ["editor"], "match": {"class": "["}}
                        ],
                    }
                )
            )

    def test_rejects_out_of_range_volume(self):
        with self.assertRaisesRegex(ConfigError, "between 0 and 100"):
            validate_config(
                config_with(
                    {
                        "id": "meeting",
                        "name": "Meeting",
                        "audio": {"inputVolume": 101},
                    }
                )
            )

    def test_load_reports_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenes.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "invalid JSON"):
                load_config(path)


class PlanningTests(unittest.TestCase):
    def test_builds_ordered_native_commands(self):
        scene = {
            "id": "work",
            "name": "Work",
            "before": [["prepare", "--quiet"]],
            "monitors": [
                {
                    "name": "DP-1",
                    "mode": "2560x1440@144",
                    "position": "0x0",
                    "scale": 1,
                }
            ],
            "audio": {
                "output": "42",
                "outputVolume": 35,
                "outputMuted": False,
            },
            "dnd": True,
            "powerProfile": "balanced",
            "nightLight": False,
            "theme": "Tokyo Night",
            "wallpaper": "~/wallpaper.png",
            "after": [["notify", "ready"]],
        }
        actions = plan_scene(scene)
        self.assertEqual(actions[0].command, ("prepare", "--quiet"))
        self.assertEqual(
            actions[1].command,
            ("hyprctl", "keyword", "monitor", "DP-1,2560x1440@144,0x0,1"),
        )
        self.assertIn(
            ("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "35%"),
            [action.command for action in actions],
        )
        self.assertIn(
            ("omarchy-shell", "notifications", "setDnd", "true"),
            [action.command for action in actions],
        )
        self.assertEqual(actions[-1].command, ("notify", "ready"))

    def test_monitor_can_be_disabled(self):
        actions = plan_scene(
            {"id": "travel", "name": "Travel", "monitors": [{"name": "DP-1", "disabled": True}]}
        )
        self.assertEqual(
            actions[0].command, ("hyprctl", "keyword", "monitor", "DP-1,disable")
        )


class ApplyTests(unittest.TestCase):
    def test_optional_failure_keeps_scene_active_with_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"

            def runner(command):
                return 127, "powerprofilesctl is not installed"

            state = apply_scene(
                {"id": "travel", "name": "Travel", "powerProfile": "power-saver"},
                runner=runner,
                state_path=state_path,
            )
            self.assertEqual(state["active"], "travel")
            self.assertEqual(state["phase"], "applied-with-warnings")
            self.assertEqual(read_state(state_path), state)

    def test_required_hook_failure_stops_transition(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state = apply_scene(
                {
                    "id": "work",
                    "name": "Work",
                    "before": [["prepare"]],
                    "powerProfile": "balanced",
                },
                runner=lambda command: (1, "no") if command[0] == "prepare" else (0, ""),
                state_path=state_path,
            )
            self.assertEqual(state["phase"], "failed")
            self.assertEqual(state["active"], "")

    def test_after_hook_runs_after_scene_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def runner(command):
                calls.append(tuple(command))
                return 0, ""

            apply_scene(
                {
                    "id": "work",
                    "name": "Work",
                    "powerProfile": "balanced",
                    "after": [["notify", "ready"]],
                },
                runner=runner,
                state_path=Path(directory) / "state.json",
            )
            self.assertEqual(
                calls,
                [
                    ("powerprofilesctl", "set", "balanced"),
                    ("notify", "ready"),
                ],
            )

    def test_dry_run_does_not_write_state_or_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            calls = []
            state = apply_scene(
                {"id": "work", "name": "Work", "before": [["prepare"]]},
                runner=lambda command: calls.append(command) or (0, ""),
                state_path=state_path,
                dry_run=True,
            )
            self.assertEqual(state["phase"], "active")
            self.assertEqual(calls, [])
            self.assertFalse(state_path.exists())


if __name__ == "__main__":
    unittest.main()
