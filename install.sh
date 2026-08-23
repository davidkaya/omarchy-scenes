#!/usr/bin/env bash
set -euo pipefail

plugin_id="io.github.davidkaya.omarchy-scenes"
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target_dir="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/$plugin_id"
config_file="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/scenes.json"
bin_dir="${HOME}/.local/bin"

mkdir -p "$target_dir" "$(dirname "$config_file")" "$bin_dir"
find "$target_dir" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
cp -a "$source_dir"/manifest.json "$source_dir"/*.qml "$source_dir"/bin "$source_dir"/src "$target_dir"/
chmod +x "$target_dir/bin/omarchy-scenes"
ln -sfn "$target_dir/bin/omarchy-scenes" "$bin_dir/omarchy-scenes"

if [[ ! -e "$config_file" ]]; then
  cp "$source_dir/examples/scenes.json" "$config_file"
  printf 'Created %s\n' "$config_file"
fi

omarchy-shell shell rescanPlugins
omarchy plugin enable "$plugin_id"
printf 'Installed %s. Edit %s, then run: omarchy-shell %s reload\n' "$plugin_id" "$config_file" "$plugin_id"
