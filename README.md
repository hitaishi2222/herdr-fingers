# herdr-fingers

Extract file paths, URLs, IPs, UUIDs, hashes, and other identifiers from the focused terminal pane and pick one with **vimium-style letter keys**.

Inspired by [tmux-fingers](https://github.com/Morantron/tmux-fingers).

![herdr-fingers screenshot](herdr-fingers.png)

## How it works

1. Press `alt+f` in any Herdr pane.
2. The plugin scans the **visible content** of the focused pane for 11 pattern types.
3. Findings are shown in a fuzzy-search picker (InquirerPy or fzf).
4. Type to filter, press Enter to select — the value is copied to your clipboard.
5. The overlay closes automatically.

Press `Esc` to cancel.

### Search engine

Configure in `~/.config/herdr/plugins/config/herdr-fingers/config.toml`:

```toml
# Choose: "inquirerpy" or "fzf"
# Default: auto-detect (InquirerPy → fzf)
search_engine = "inquirerpy"

# Extra CLI args for fzf (array of strings).
# Appended after our defaults. Provide a non-empty list to omit defaults.
# fzf_args = ["--multi", "--preview", "echo {}"]

# Command used by the open action. The selected value is appended as the final
# argument.
# open_command = "~/.config/nvim/bin/open-path-in-nvim"
```

If no engine is configured, the plugin auto-detects the best available one.
If none is found, it falls back to the letter-key picker and prints install instructions.

## Pattern types

| Type                | Example                                        |
| ------------------- | ---------------------------------------------- |
| `ip`                | `192.168.1.100`                                |
| `uuid`              | `550e8400-e29b-41d4-a716-446655440000`         |
| `sha`               | `8b1a9953c4611299a820df69698463c3ca01599d`     |
| `url`               | `https://example.com/path`                     |
| `path`              | `/home/user/documents/file.txt`, `/etc/config` |
| `color`             | `#FF5733`                                      |
| `hex`               | `0xDEADBEEF`                                   |
| `kubernetes`        | `my-app.default.svc.cluster.local`             |
| `git-status`        | `M src/main.py` (from `git status`)            |
| `git-status-branch` | `main` (from `git status` branch line)         |
| `digit`             | `12345678` (4+ digit numbers)                  |

## Installation

```bash
herdr plugin install hitaishi2222/herdr-fingers
```

for development:

```bash
git clone https://https://github.com/hitaishi2222/herdr-fingers
cd herdr-fingers
herdr plugin link .
```

Then bind a key of your choice in your `~/.config/herdr/config.toml`:

```toml
[[keys.command]]
key = "alt+f"  # change to whatever you like
```

Keep `type = "plugin_action"` and `command = "herdr-fingers.finger"` the same.

```toml
[[keys.command]]
key = "alt+f"
type = "plugin_action"
command = "herdr-fingers.finger"
description = "Fingers"
```

To open the selected finding with a custom command instead of copying it, bind
the `herdr-fingers.open` action and configure `open_command`:

```toml
[[keys.command]]
key = "alt+shift+f"
type = "plugin_action"
command = "herdr-fingers.open"
description = "Fingers: open"
```

## Requirements

- Herdr ≥ 0.7.0
- Python 3.12+
- One of: **InquirerPy** (`pip install InquirerPy`) or **fzf** (for fuzzy search)
- One of: `wl-copy`, `xclip`, `xsel`, or `pbcopy` (for clipboard access)

## Limits

- Max **676 items** (InquirerPy / fzf handle larger lists gracefully)
- Items longer than 60 chars are truncated in the display (full value is still copied)
- Only extracts from the **currently focused pane's visible content**

## About

Written by me with some help from AI. Found a bug or have an idea? [Open an issue](../../issues).

## License

MIT
