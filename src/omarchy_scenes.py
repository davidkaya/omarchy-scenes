#!/usr/bin/env python3
"""Declarative desktop scene orchestration for Omarchy."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

PLUGIN_ID = "io.github.davidkaya.omarchy-scenes"
DEFAULT_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarchy" / "scenes.json"
DEFAULT_STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "omarchy-scenes" / "state.json"
SCENE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
LEGACY_TERMINAL_COMMAND = ["uwsm-app", "--", "ghostty"]
DEFAULT_TERMINAL_COMMAND = ["omarchy-launch-terminal"]


class ConfigError(ValueError):
    """Raised when a scene configuration is invalid."""


@dataclass(frozen=True)
class Action:
    label: str
    command: tuple[str, ...]
    optional: bool = True
    stage: str = "main"


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{location} must be a non-empty string")
    return value


def _command(value: Any, location: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(part, str) and part for part in value)
    ):
        raise ConfigError(f"{location} must be a non-empty array of strings")
    return tuple(value)


def validate_config(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ConfigError("configuration must be an object")
    if data.get("schemaVersion") != 1:
        raise ConfigError("schemaVersion must be 1")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ConfigError("scenes must be a non-empty array")

    seen: set[str] = set()
    for index, scene in enumerate(scenes):
        where = f"scenes[{index}]"
        if not isinstance(scene, dict):
            raise ConfigError(f"{where} must be an object")
        scene_id = _string(scene.get("id"), f"{where}.id")
        if not SCENE_ID_RE.fullmatch(scene_id):
            raise ConfigError(f"{where}.id contains unsupported characters")
        if scene_id in seen:
            raise ConfigError(f"duplicate scene id: {scene_id}")
        seen.add(scene_id)
        _string(scene.get("name"), f"{where}.name")
        if "icon" in scene:
            _string(scene["icon"], f"{where}.icon")

        for hook in ("before", "after"):
            if hook in scene:
                if not isinstance(scene[hook], list):
                    raise ConfigError(f"{where}.{hook} must be an array")
                for command_index, command in enumerate(scene[hook]):
                    _command(command, f"{where}.{hook}[{command_index}]")

        if "monitors" in scene:
            if not isinstance(scene["monitors"], list):
                raise ConfigError(f"{where}.monitors must be an array")
            for monitor_index, monitor in enumerate(scene["monitors"]):
                monitor_where = f"{where}.monitors[{monitor_index}]"
                if not isinstance(monitor, dict):
                    raise ConfigError(f"{monitor_where} must be an object")
                _string(monitor.get("name"), f"{monitor_where}.name")
                if monitor.get("disabled") is not True:
                    _string(monitor.get("mode", "preferred"), f"{monitor_where}.mode")
                    _string(monitor.get("position", "auto"), f"{monitor_where}.position")
                    scale = monitor.get("scale", 1)
                    if not isinstance(scale, (int, float)) or scale <= 0:
                        raise ConfigError(f"{monitor_where}.scale must be positive")
                    if "transform" in monitor and (
                        not isinstance(monitor["transform"], int)
                        or not 0 <= monitor["transform"] <= 7
                    ):
                        raise ConfigError(f"{monitor_where}.transform must be an integer from 0 to 7")

        if "audio" in scene:
            audio = scene["audio"]
            if not isinstance(audio, dict):
                raise ConfigError(f"{where}.audio must be an object")
            for key in ("output", "input"):
                if key in audio:
                    _string(audio[key], f"{where}.audio.{key}")
            for key in ("outputVolume", "inputVolume"):
                if key in audio and (
                    not isinstance(audio[key], (int, float)) or not 0 <= audio[key] <= 100
                ):
                    raise ConfigError(f"{where}.audio.{key} must be between 0 and 100")
            for key in ("outputMuted", "inputMuted"):
                if key in audio and not isinstance(audio[key], bool):
                    raise ConfigError(f"{where}.audio.{key} must be boolean")

        if "applications" in scene:
            if not isinstance(scene["applications"], list):
                raise ConfigError(f"{where}.applications must be an array")
            for app_index, app in enumerate(scene["applications"]):
                app_where = f"{where}.applications[{app_index}]"
                if not isinstance(app, dict):
                    raise ConfigError(f"{app_where} must be an object")
                _command(app.get("command"), f"{app_where}.command")
                match = app.get("match")
                if not isinstance(match, dict) or not any(key in match for key in ("class", "title")):
                    raise ConfigError(f"{app_where}.match must contain class or title")
                for key in ("class", "title"):
                    if key in match:
                        pattern = _string(match[key], f"{app_where}.match.{key}")
                        try:
                            re.compile(pattern)
                        except re.error as error:
                            raise ConfigError(f"{app_where}.match.{key} is invalid: {error}") from error
                if "workspace" in app:
                    _string(str(app["workspace"]), f"{app_where}.workspace")

        if "dnd" in scene and not isinstance(scene["dnd"], bool):
            raise ConfigError(f"{where}.dnd must be boolean")
        if "nightLight" in scene and not isinstance(scene["nightLight"], bool):
            raise ConfigError(f"{where}.nightLight must be boolean")
        for key in ("powerProfile", "theme", "wallpaper"):
            if key in scene:
                _string(scene[key], f"{where}.{key}")
    return data


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            config = validate_config(json.load(handle))
        for scene in config["scenes"]:
            for application in scene.get("applications", []):
                if application["command"] == LEGACY_TERMINAL_COMMAND:
                    application["command"] = DEFAULT_TERMINAL_COMMAND.copy()
        return config
    except FileNotFoundError as error:
        raise ConfigError(f"configuration not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"invalid JSON in {path}: {error}") from error


def scene_by_id(config: dict[str, Any], scene_id: str) -> dict[str, Any]:
    for scene in config["scenes"]:
        if scene["id"] == scene_id:
            return scene
    raise ConfigError(f"unknown scene: {scene_id}")


def _lua_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value))


def _monitor_expression(monitor: dict[str, Any]) -> str:
    if monitor.get("disabled") is True:
        values = {"output": monitor["name"], "disabled": True}
    else:
        values = {
            "output": monitor["name"],
            "mode": monitor.get("mode", "preferred"),
            "position": monitor.get("position", "auto"),
            "scale": monitor.get("scale", 1),
        }
    if "transform" in monitor:
        values["transform"] = monitor["transform"]
    fields = ", ".join(f"{key} = {_lua_literal(value)}" for key, value in values.items())
    return f"hl.monitor({{ {fields} }})"


def plan_scene(scene: dict[str, Any]) -> list[Action]:
    actions: list[Action] = []
    for command in scene.get("before", []):
        actions.append(Action("before hook", tuple(command), False, "before"))
    for monitor in scene.get("monitors", []):
        actions.append(
            Action(
                f"monitor {monitor['name']}",
                ("hyprctl", "eval", _monitor_expression(monitor)),
            )
        )

    audio = scene.get("audio", {})
    if "output" in audio:
        actions.append(Action("audio output", ("wpctl", "set-default", audio["output"])))
    if "input" in audio:
        actions.append(Action("audio input", ("wpctl", "set-default", audio["input"])))
    for key, target in (
        ("outputVolume", "@DEFAULT_AUDIO_SINK@"),
        ("inputVolume", "@DEFAULT_AUDIO_SOURCE@"),
    ):
        if key in audio:
            actions.append(Action(key, ("wpctl", "set-volume", target, f"{audio[key]:g}%")))
    for key, target in (
        ("outputMuted", "@DEFAULT_AUDIO_SINK@"),
        ("inputMuted", "@DEFAULT_AUDIO_SOURCE@"),
    ):
        if key in audio:
            actions.append(Action(key, ("wpctl", "set-mute", target, "1" if audio[key] else "0")))

    if "dnd" in scene:
        actions.append(Action("do not disturb", ("omarchy-shell", "notifications", "setDnd", str(scene["dnd"]).lower())))
    if "powerProfile" in scene:
        actions.append(
            Action(
                "power profile",
                ("omarchy-powerprofiles-set", "autodetect", scene["powerProfile"]),
            )
        )
    if "nightLight" in scene:
        actions.append(Action("night light", ("omarchy-shell", "nightlight", "enable" if scene["nightLight"] else "disable")))
    if "theme" in scene:
        actions.append(Action("theme", ("omarchy-theme-set", scene["theme"])))
    if "wallpaper" in scene:
        actions.append(Action("wallpaper", ("omarchy-theme-bg-set", os.path.expanduser(scene["wallpaper"]))))
    for command in scene.get("after", []):
        actions.append(Action("after hook", tuple(command), False, "after"))
    return actions


def printable_plan(scene: dict[str, Any]) -> list[dict[str, Any]]:
    actions = plan_scene(scene)
    result = [
        {"label": action.label, "command": list(action.command)}
        for action in actions
        if action.stage != "after"
    ]
    result.extend(
        {
            "label": "application",
            "command": app["command"],
            "match": app["match"],
            **({"workspace": str(app["workspace"])} if "workspace" in app else {}),
        }
        for app in scene.get("applications", [])
    )
    result.extend(
        {"label": action.label, "command": list(action.command)}
        for action in actions
        if action.stage == "after"
    )
    return result


def _clients() -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            ["hyprctl", "clients", "-j"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        parsed = json.loads(result.stdout)
        return parsed if isinstance(parsed, list) else []
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []


def _matching_clients(app: dict[str, Any], clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    match = app["match"]
    found = []
    for client in clients:
        class_value = str(client.get("class") or client.get("initialClass") or "")
        title_value = str(client.get("title") or client.get("initialTitle") or "")
        if "class" in match and re.search(match["class"], class_value, re.IGNORECASE) is None:
            continue
        if "title" in match and re.search(match["title"], title_value, re.IGNORECASE) is None:
            continue
        found.append(client)
    return found


def _workspace_move_expression(workspace: str, address: str) -> str:
    normalized_address = address if address.startswith("0x") else f"0x{address}"
    return (
        "hl.dsp.window.move({ "
        f"workspace = {_lua_literal(workspace)}, "
        f"window = {_lua_literal(f'address:{normalized_address}')}, "
        "follow = false })"
    )


def apply_applications(
    applications: list[dict[str, Any]],
    *,
    timeout: float = 10,
) -> list[str]:
    warnings: list[str] = []
    for app in applications:
        matches = _matching_clients(app, _clients())
        if not matches:
            try:
                subprocess.Popen(
                    app["command"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError as error:
                warnings.append(f"application {' '.join(app['command'])}: {error}")
                continue
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                time.sleep(0.2)
                matches = _matching_clients(app, _clients())
                if matches:
                    break
        if not matches:
            warnings.append(f"application did not open: {' '.join(app['command'])}")
            continue
        workspace = app.get("workspace")
        if workspace is not None:
            for client in matches:
                address = str(client.get("address", ""))
                if not address:
                    continue
                try:
                    result = subprocess.run(
                        [
                            "hyprctl",
                            "dispatch",
                            _workspace_move_expression(str(workspace), address),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                except (OSError, subprocess.SubprocessError):
                    warnings.append(f"could not move {address} to workspace {workspace}")
                    continue
                if result.returncode:
                    warnings.append(f"could not move {address} to workspace {workspace}")
    return warnings


def default_runner(command: Sequence[str]) -> tuple[int, str]:
    executable = command[0]
    if shutil.which(executable) is None:
        return 127, f"{executable} is not installed"
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        return 1, str(error)
    detail = (result.stderr or result.stdout).strip()
    return result.returncode, detail


def write_state(state: dict[str, Any], path: Path = DEFAULT_STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_state(path: Path = DEFAULT_STATE) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            state = json.load(handle)
        return state if isinstance(state, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _apply_scene_unlocked(
    scene: dict[str, Any],
    *,
    runner: Callable[[Sequence[str]], tuple[int, str]] = default_runner,
    state_path: Path = DEFAULT_STATE,
) -> dict[str, Any]:
    state = {
        "active": read_state(state_path).get("active", ""),
        "phase": "applying",
        "target": scene["id"],
        "warnings": [],
    }
    write_state(state, state_path)

    warnings: list[str] = []
    actions = plan_scene(scene)
    for action in (item for item in actions if item.stage != "after"):
        code, detail = runner(action.command)
        if code:
            message = f"{action.label}: {detail or f'exited with {code}'}"
            if action.optional:
                warnings.append(message)
            else:
                state.update(phase="failed", warnings=warnings, message=message)
                write_state(state, state_path)
                return state

    warnings.extend(apply_applications(scene.get("applications", [])))
    for action in (item for item in actions if item.stage == "after"):
        code, detail = runner(action.command)
        if code:
            state.update(
                phase="failed",
                warnings=warnings,
                message=f"{action.label}: {detail or f'exited with {code}'}",
            )
            write_state(state, state_path)
            return state
    state = {
        "active": scene["id"],
        "name": scene["name"],
        "icon": scene.get("icon", "󰒓"),
        "phase": "applied-with-warnings" if warnings else "active",
        "warnings": warnings,
        "updatedAt": int(time.time()),
    }
    write_state(state, state_path)
    return state


def apply_scene(
    scene: dict[str, Any],
    *,
    runner: Callable[[Sequence[str]], tuple[int, str]] = default_runner,
    state_path: Path = DEFAULT_STATE,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        return {
            "active": read_state(state_path).get("active", ""),
            "target": scene["id"],
            "name": scene["name"],
            "icon": scene.get("icon", "󰒓"),
            "phase": "dry-run",
            "warnings": [],
        }

    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _apply_scene_unlocked(
            scene,
            runner=runner,
            state_path=state_path,
        )


def _summary(config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    scenes = [
        {
            "id": scene["id"],
            "name": scene["name"],
            "icon": scene.get("icon", "󰒓"),
            "description": scene.get("description", ""),
        }
        for scene in config["scenes"]
    ]
    return {"scenes": scenes, "state": state}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omarchy-scenes")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")
    subparsers.add_parser("status")
    subparsers.add_parser("validate")
    plan = subparsers.add_parser("plan")
    plan.add_argument("scene")
    apply = subparsers.add_parser("apply")
    apply.add_argument("scene")
    apply.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "validate":
            print(json.dumps({"valid": True, "scenes": len(config["scenes"])}))
            return 0
        if args.command == "list":
            print(json.dumps(_summary(config, read_state(args.state))))
            return 0
        if args.command == "status":
            print(json.dumps(read_state(args.state)))
            return 0
        scene = scene_by_id(config, args.scene)
        if args.command == "plan":
            print(json.dumps(printable_plan(scene), indent=2))
            return 0
        state = apply_scene(scene, state_path=args.state, dry_run=args.dry_run)
        print(json.dumps(state))
        return 0 if state["phase"] in ("active", "applied-with-warnings", "dry-run") else 1
    except ConfigError as error:
        print(json.dumps({"error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
