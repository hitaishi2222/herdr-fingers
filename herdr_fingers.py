#!/usr/bin/env python3
"""
Extract file paths, URLs, IPs, UUIDs, hashes, and other identifiers from the
focused pane's visible content, display them with vimium-style letter keys,
and copy the selected item to the clipboard.

Flow:
  1. Get the focused pane ID (HERDR_PANE_ID env or herdr pane current).
  2. Read visible content via `herdr pane read --source visible`.
  3. Extract all pattern matches (11 types).
  4. Deduplicate, sort, assign letter keys.
  5. Display grouped by type.
  6. Read one keystroke (Esc cancels).
  7. Copy selected value to clipboard.
  8. Exit — herdr closes the overlay.
"""

import os
import re
import sys
import json
import shutil
import subprocess
import tty
import termios
from pathlib import Path
from rich.console import Console
from rich.text import Text

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_ITEMS = 676  # 26^2 — max items we can assign 2-letter keys to

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def herdr(*args: str) -> str:
    """Run a herdr CLI command and return stdout."""
    herdr_bin = os.environ.get("HERDR_BIN_PATH", "herdr")
    result = subprocess.run(
        [herdr_bin, *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def err(msg: str, code: int = 1) -> None:
    """Print error and exit."""
    print(f"herdr-fingers: error: {msg}", file=sys.stderr)
    sys.exit(code)


def detect_clipboard_tool():
    """Return the command list to copy to clipboard, or None."""
    for cmd, args in [
        ("wl-copy", []),       # Wayland
        ("xclip", ["-selection", "clipboard"]),  # X11
        ("xsel", ["--clipboard", "--input"]),     # X11 alt
        ("pbcopy", []),       # macOS
    ]:
        if shutil.which(cmd):
            return [cmd, *args]
    return None


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Each pattern: (name, compiled_regex, priority)
# Priority: higher = more specific, checked first for overlap resolution.

PATTERNS = [
    # (name, regex, priority)
    ("uuid", re.compile(
        r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
    ), 100),

    ("sha", re.compile(
        r'\b[0-9a-fA-F]{40}\b'
    ), 90),

    ("ip", re.compile(
        r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'
    ), 80),

    ("url", re.compile(
        r'(?:(?:https?|git|ssh|file|ftps?)://)[^\s<>"\'`)\]]+',
        re.IGNORECASE
    ), 70),

    # Kubernetes: requires hyphen in name + multi-label domain
    ("kubernetes", re.compile(
        r'\b[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])\.(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)*\.[a-z]{2,}\b'
    ), 60),
    # Path: ~/something or /<sysdir>/... (min 3 chars)
    ("path", re.compile(
        r'~/[\w./-]{2,}|/(boot|dev|etc|home|mnt|opt|proc|root|run|srv|sys|tmp|usr)[\w./-]*',
    ), 50),

    ("hex", re.compile(
        r'\b0x[0-9a-fA-F]{2,}\b'
    ), 40),

    # Digit: 4+ digits, but not part of hex (0x...) or UUID
    ("digit", re.compile(
        r'(?<!x)(?<!\d)\d{4,}(?!\d)'
    ), 30),

    ("git-status", re.compile(
        r'^\s*[RAMDU?][ \t]+(.+)$',
        re.MULTILINE
    ), 20),

    ("git-status-branch", re.compile(
        r'^# On branch (.+)$|^# branch (.+)$',
        re.MULTILINE
    ), 15),

    ("diff", re.compile(
        r'^diff --git a/.+ b/(.+)$',
        re.MULTILINE
    ), 10),
]


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_items(text: str) -> list[tuple[str, str, int]]:
    """
    Extract all pattern matches from text.
    Returns list of (type, value, position) tuples, deduplicated.
    """
    seen: set[tuple[str, str]] = set()
    items: list[tuple[str, str, int]] = []

    for type_name, pattern, _priority in PATTERNS:
        for m in pattern.finditer(text):
            value = m.group(0)
            key = (type_name, value)
            if key not in seen:
                seen.add(key)
                items.append((type_name, value, m.start()))

    # Sort by type name, then position
    items.sort(key=lambda x: (x[0], x[2]))

    # Remove matches that are substrings of higher-priority matches
    # (e.g., /path inside a URL match)
    items = _remove_overlapping(items, text)

    # Filter path items: keep only valid paths (exists or has valid structure)
    items = _filter_valid_paths(items)

    return items


def _remove_overlapping(items: list[tuple[str, str, int]], text: str) -> list[tuple[str, str, int]]:
    """
    Remove items whose span is fully contained within another item's span.
    Preserves the outer (higher-priority) match.
    """
    # Sort by span length descending (longer spans first)
    sorted_items = sorted(items, key=lambda x: -len(x[1]))
    result = []
    for item in sorted_items:
        start, end = item[2], item[2] + len(item[1])
        # Check if this item is contained in any already-kept item
        contained = False
        for kept in result:
            ks, ke = kept[2], kept[2] + len(kept[1])
            if ks <= start and end <= ke:
                contained = True
                break
        if not contained:
            result.append(item)
    # Restore sort by type, then position
    result.sort(key=lambda x: (x[0], x[2]))
    return result


def _filter_valid_paths(items: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    """
    Filter path items: keep only valid paths (exists or has valid structure).
    Uses pathlib to validate.
    """
    result = []
    for type_name, value, pos in items:
        if type_name != "path":
            result.append((type_name, value, pos))
            continue
        # Skip URLs (contain :// or start with //)
        if "://" in value or value.startswith("//"):
            continue
        # Try to resolve with pathlib
        try:
            p = Path(value)
            # Keep if it exists or has a valid absolute/tilde path structure
            if p.exists() or p.is_absolute() or str(p).startswith("~/"):
                result.append((type_name, value, pos))
        except (ValueError, TypeError, PermissionError, OSError):
            # Invalid path or unreadable — keep it, the user sees it
            result.append((type_name, value, pos))
    return result


# ---------------------------------------------------------------------------
# Letter key assignment
# ---------------------------------------------------------------------------

def assign_keys(items: list[tuple[str, str, int]]) -> list[tuple[str, str, int, str]]:
    """
    Assign vimium-style letter keys to items.
    Returns items with keys appended: [(type, value, pos, key), ...]
    """
    n = len(items)
    if n == 0:
        return []

    result = []
    for i, item in enumerate(items):
        if i < 26:
            key = chr(ord('a') + i)
        else:
            # Two-letter keys: aa, ab, ..., az, ba, ..., zz
            first = i // 26 - 1
            second = i % 26
            key = chr(ord('a') + first) + chr(ord('a') + second)
        result.append((*item, key))

    return result


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

# Color mapping for different item types
TYPE_COLORS = {
    "uuid": "magenta",
    "sha": "magenta",
    "ip": "cyan",
    "url": "blue",
    "kubernetes": "cyan",
    "path": "green",
    "hex": "yellow",
    "digit": "yellow",
    "git-status": "red",
    "git-status-branch": "red",
    "diff": "red",
}


def format_display(items_with_keys: list[tuple[str, str, int, str]]) -> list[Text]:
    """Format items grouped by type for display using rich."""
    if not items_with_keys:
        return [Text("No items found.")]

    # Group by type
    from collections import OrderedDict
    groups: dict[str, list[tuple[str, str, int, str]]] = OrderedDict()
    for item in items_with_keys:
        type_name = item[0]
        groups.setdefault(type_name, []).append(item)

    output: list[Text] = []
    output.append(Text(f"Found {len(items_with_keys)} items. Press a key to copy:"))
    output.append(Text())  # blank line

    for type_name, group in groups.items():
        color = TYPE_COLORS.get(type_name, "white")
        header = Text(f"  {type_name} ({len(group)}):", style=color)
        header.stylize("bold")
        output.append(header)

        for _, value, _, key in group:
            # Truncate long values
            display_value = value if len(value) <= 60 else value[:57] + "..."
            line = Text(f"    {key}: ", style="bold cyan")
            line.append(display_value)
            output.append(line)

        output.append(Text())  # blank line

    output.append(Text("Esc: cancel", style="dim"))
    return output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def wait_for_key(message: str = "Press any key to close..."):
    """Wait for a keypress, then exit. Used for error/non-finding states."""
    print(f"\n{message}", file=sys.stderr)
    key = ""
    try:
        if sys.stdin.isatty():
            try:
                old_attrs = termios.tcgetattr(sys.stdin.fileno())
                try:
                    tty.setcbreak(sys.stdin.fileno())
                    key = sys.stdin.read(1)
                finally:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attrs)
            except (termios.error, IOError, OSError):
                try:
                    with open("/dev/tty", "r") as tty_file:
                        key = tty_file.read(1)
                except (IOError, OSError):
                    pass
        else:
            try:
                with open("/dev/tty", "r") as tty_file:
                    key = tty_file.read(1)
            except (IOError, OSError):
                pass
    except KeyboardInterrupt:
        key = "\x1b"  # Esc
    print("Exiting.", file=sys.stderr)
    sys.exit(0)


def main():
    content_path = "/tmp/herdr-fingers-content"
    try:
        # Read pane content from well-known path (set by shell script before overlay opens)
        if not os.path.exists(content_path):
            print("No pane content available.")
            wait_for_key("Press any key to close...")

        with open(content_path) as f:
            text = f.read()

        if not text.strip():
            print("Pane appears empty.")
            wait_for_key("Press any key to close...")

        # 3. Extract items
        items = extract_items(text)

        if not items:
            print("No items found in pane.")
            wait_for_key("Press any key to close...")

        # 4. Assign keys
        items_with_keys = assign_keys(items)

        # 5. Display
        display_lines = format_display(items_with_keys)
        console = Console()
        for line in display_lines:
            console.print(line)

        # 6. Read keystroke
        print("\nWaiting for key...", file=sys.stderr)

        # Save and disable echo
        old_stty = None
        key = ""
        try:
            # Try to save and disable echo via stty
            try:
                stty_result = subprocess.run(
                    ["stty", "-g"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                # Strip newlines from stty output
                old_stty = stty_result.stdout.strip().replace("\n", "")
                subprocess.run(["stty", "-echo"], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
                # stty not available or failed — continue without echo control
                old_stty = None

            # Read single keystroke
            if sys.stdin.isatty():
                try:
                    old_attrs = termios.tcgetattr(sys.stdin.fileno())
                    try:
                        tty.setcbreak(sys.stdin.fileno())
                        key = sys.stdin.read(1)
                    finally:
                        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attrs)
                except (termios.error, IOError, OSError):
                    # Fallback: try /dev/tty
                    try:
                        with open("/dev/tty", "r") as tty_file:
                            key = tty_file.read(1)
                    except (IOError, OSError):
                        pass
            else:
                # No TTY — try /dev/tty
                try:
                    with open("/dev/tty", "r") as tty_file:
                        key = tty_file.read(1)
                except (IOError, OSError):
                    pass
        except KeyboardInterrupt:
            key = "\x1b"  # Esc
        finally:
            # Restore echo if we changed it
            if old_stty:
                try:
                    subprocess.run(["stty", old_stty], check=True)
                except subprocess.CalledProcessError:
                    pass

        if not key or key == "\x1b":
            # Esc or no key — cancel
            print("Cancelled.", file=sys.stderr)
            # Restore terminal and exit
            if old_stty:
                try:
                    subprocess.run(["stty", old_stty], check=False)
                except Exception:
                    pass
            sys.exit(0)

        # Case-insensitive key lookup
        key_lower = key.lower()

        # 7. Find selected item
        selected = None
        for item in items_with_keys:
            if item[3].lower() == key_lower:
                selected = item
                break

        if not selected:
            print(f"Unknown key: {key}")
            wait_for_key("Press any key to close...")

        value = selected[1]

        # 8. Copy to clipboard
        clip_tool = detect_clipboard_tool()
        if not clip_tool:
            err("no clipboard tool found (need wl-copy, xclip, xsel, or pbcopy)")

        try:
            subprocess.run(
                clip_tool,
                input=value,
                text=True,
                check=True,
            )
            # Show notification
            display_value = value if len(value) <= 60 else value[:57] + "..."
            subprocess.run(
                ["herdr", "notification", "show", "Copied", "--body", display_value],
                check=False,
            )
        except subprocess.CalledProcessError as e:
            err(f"clipboard copy failed: {e.stderr}")

    except Exception as e:
        # Catch-all: show error and wait for key before closing
        print(f"\nherdr-fingers: error: {e}", file=sys.stderr)
        wait_for_key("Press any key to close...")
    finally:
        # Clean up temp file
        try:
            os.remove(content_path)
        except OSError:
            pass
    



if __name__ == "__main__":
    main()
