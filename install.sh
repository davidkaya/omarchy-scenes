#!/usr/bin/env bash
set -euo pipefail

plugin_id="io.github.davidkaya.omarchy-scenes"
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target_dir="$HOME/.config/omarchy/plugins/$plugin_id"
config_file="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/scenes.json"
bin_dir="${HOME}/.local/bin"
stage_dir="$HOME/.config/omarchy/plugins/.scenes-install.$$"

trap 'rm -rf -- "$stage_dir"' EXIT
mkdir -p "$(dirname "$target_dir")" "$(dirname "$config_file")" "$bin_dir" "$stage_dir"
cp -a "$source_dir"/manifest.json "$source_dir"/*.qml "$source_dir"/bin "$source_dir"/src "$stage_dir"/
chmod +x "$stage_dir/bin/omarchy-scenes"
omarchy plugin validate "$stage_dir"
rm -rf -- "$target_dir"
mv "$stage_dir" "$target_dir"
ln -sfn "$target_dir/bin/omarchy-scenes" "$bin_dir/omarchy-scenes"

if [[ ! -e "$config_file" ]]; then
  cp "$source_dir/examples/scenes.json" "$config_file"
  printf 'Created %s\n' "$config_file"
fi

omarchy-shell shell rescanPlugins
discovered=0
for ((attempt = 0; attempt < 40; attempt++)); do
  if omarchy plugin list --json | jq -e --arg id "$plugin_id" \
    'any(.[]; .id == $id)' >/dev/null; then
    discovered=1
    break
  fi
  sleep 0.05
done
((discovered)) || {
  printf 'Plugin %s was not discovered\n' "$plugin_id" >&2
  exit 1
}
omarchy plugin enable "$plugin_id"
printf 'Installed %s. Edit %s, then run: omarchy-shell %s reload\n' "$plugin_id" "$config_file" "$plugin_id"
