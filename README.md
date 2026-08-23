# Omarchy Scenes

One-click desktop contexts for Omarchy Quattro. A scene can coordinate
monitors, applications and workspaces, audio, notifications, power, night
light, theme, wallpaper, and optional commands.

This repository is intended for local validation. It is not published to a
plugin marketplace.

## Install locally

Requires Omarchy Quattro with `omarchy-shell`, Python 3, and the commands used
by your scenes.

```bash
./install.sh
```

The installer copies the plugin to
`~/.config/omarchy/plugins/io.github.davidkaya.omarchy-scenes`, creates
`~/.config/omarchy/scenes.json` on first install, and enables the plugin.
Restart the shell if it does not hot-reload:

```bash
omarchy-restart-shell
```

Click the Scenes bar widget to open the switcher. You can also use:

```bash
omarchy-scenes list
omarchy-scenes validate
omarchy-scenes plan work
omarchy-scenes apply work --dry-run
omarchy-scenes apply work
omarchy-shell io.github.davidkaya.omarchy-scenes apply work
```

## Configuration

Start with [`examples/scenes.json`](examples/scenes.json). All properties other
than `id` and `name` are optional; omitted properties are left unchanged.

| Property | Meaning |
| --- | --- |
| `icon`, `description` | Switcher presentation |
| `before`, `after` | Required commands, each represented as an argument array |
| `monitors` | Hyprland monitor definitions (`name`, `mode`, `position`, `scale`, optional `transform` or `disabled`) |
| `audio` | PipeWire device IDs, volumes from 0–100, and mute state |
| `dnd` | Omarchy notification do-not-disturb state |
| `powerProfile` | `powerprofilesctl` profile |
| `nightLight` | Omarchy night-light state |
| `theme` | Omarchy theme name |
| `wallpaper` | Wallpaper path |
| `applications` | Commands, class/title regular expressions, and optional target workspaces |

Example application:

```json
{
  "command": ["uwsm-app", "--", "ghostty"],
  "match": {"class": "com\\.mitchellh\\.ghostty"},
  "workspace": "1"
}
```

Existing matching windows are reused. Missing applications are launched
without a shell and then moved after their Hyprland window appears. Hooks are
also argument arrays and are never evaluated through a shell.

Transitions are serialized by the shell service. Unsupported optional desktop
capabilities produce warnings while the rest of the scene continues; a failed
`before` or `after` hook fails the transition. State and warnings are written
atomically to `~/.local/state/omarchy-scenes/state.json`.

After editing the configuration, reload it with:

```bash
omarchy-shell io.github.davidkaya.omarchy-scenes reload
```

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q src bin tests
```
