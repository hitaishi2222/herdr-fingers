# Implementation Plan: Fuzzy Search for herdr-fingers

## Overview

Add fuzzy-search selection to replace (or augment) the current vimium-style letter-key picker. Users pick the search engine in their plugin config — either **InquirerPy** (pure Python, no extra deps) or **fzf/skim** (external CLI). The same extracted finding list is fed to whichever engine is configured, and the selected value is copied to clipboard as before.

## Architecture Decisions

- **Engine selector in user config.** One key (`search_engine`) with values `inquirerpy`, `fzf`, or `skim`. Default: auto-detect — InquirerPy > fzf > skim. If none available, error with install instructions.
- **Config location.** `~/.config/herdr/plugins/config/herdr-fingers/config.toml` — follows the same pattern herdr-plus uses.
- **Fallback chain.** If the configured engine is missing (e.g., user picked `fzf` but it's not installed), print a clear error and exit — don't silently degrade to letter keys. We can add auto-fallback later if needed.
- **Keep letter keys as escape hatch.** If no engine is configured AND no engine is found, fall back to the existing letter-key display. This preserves backward compatibility for the published plugin (no config needed).
- **Single dispatch function.** `pick_with_engine(items_with_keys, engine)` returns the selected value. Both engines produce the same output: a single string. This keeps `main()` unchanged.

## Task List

### Task 1: Config reader + engine dispatch skeleton

**Description:** Add a config loader that reads `~/.config/herdr/plugins/config/herdr-fingers/config.toml` (if it exists) and returns the `search_engine` setting. Add a dispatch function `pick_with_engine(items, engine)` that routes to the right picker.

**Acceptance criteria:**
- [ ] `load_config()` returns `{"search_engine": "fzf"}` (default) when no config file exists
- [ ] `load_config()` reads `search_engine` from the TOML file when it exists
- [ ] `pick_with_engine()` dispatches to the correct function based on engine name
- [ ] Unknown engine name returns a clear error message

**Verification:**
- [ ] `python3 -c "from herdr_fingers import load_config; print(load_config())"` prints default
- [ ] Create a temp config file and verify it's read correctly

**Dependencies:** None

**Files likely touched:**
- `herdr_fingers.py`

**Estimated scope:** XS (a few new functions)

---

### Task 2: InquirerPy picker

**Description:** Implement `pick_with_inquirerpy(items_with_keys)` that displays findings grouped by type and lets the user fuzzy-search and select one. Uses InquirerPy's `Inquirer` with a list prompt.

**Acceptance criteria:**
- [ ] Displays all findings in a scrollable, searchable list
- [ ] Items grouped by type with type headers
- [ ] User can type to filter, arrow keys to navigate, Enter to select
- [ ] Esc cancels (returns None)
- [ ] Returns the selected value string, or None on cancel

**Verification:**
- [ ] Run with sample data, confirm fuzzy search works
- [ ] Confirm Esc cancels cleanly

**Dependencies:** Task 1

**Files likely touched:**
- `herdr_fingers.py`

**Estimated scope:** S (one new function + InquirerPy import)

---

### Task 3: fzf picker

**Description:** Implement `pick_with_fzf(items_with_keys)` that pipes findings to `fzf` and reads the selected line. Uses fzf's `--ansi` for colored output, `--preview` optional, and `--expect` for multi-key support.

**Acceptance criteria:**
- [ ] Pipes formatted findings to fzf stdin
- [ ] fzf displays with type grouping (using ANSI headers or separator lines)
- [ ] User can type to fuzzy-filter
- [ ] Enter selects, Esc cancels
- [ ] Returns the selected value string, or None on cancel
- [ ] Gracefully errors if fzf is not installed

**Verification:**
- [ ] Run with sample data, confirm fzf launches and filters correctly
- [ ] Confirm Esc exits without copying anything

**Dependencies:** Task 1

**Files likely touched:**
- `herdr_fingers.py`

**Estimated scope:** S (one new function)

---

### Task 4: skim picker

**Description:** Implement `pick_with_skim(items_with_keys)` — same interface as fzf but calls `skim` instead. Skim's CLI is largely fzf-compatible.

**Acceptance criteria:**
- [ ] Same behavior as fzf picker but invokes `skim`
- [ ] Gracefully errors if skim is not installed

**Verification:**
- [ ] Run with sample data if skim is available

**Dependencies:** Task 3 (skim is fzf's sibling; same approach)

**Files likely touched:**
- `herdr_fingers.py`

**Estimated scope:** XS (copy of fzf picker, swap binary name)

---

### Task 5: Wire into main() + format for pickers

**Description:** Modify `main()` to: load config, pick the engine, and route to the picker instead of the letter-key display. Add a `format_for_picker()` helper that produces the text lines the pickers consume (type headers + items with keys). Also add a fallback path: if no engine is configured and none is detected, fall back to the existing letter-key display.

**Acceptance criteria:**
- [ ] When `search_engine` is set and the binary/lib is available, the picker replaces the letter-key display
- [ ] When engine is missing, clear error message suggesting how to fix it
- [ ] When no config exists, falls back to letter-key display (backward compat)
- [ ] Selection still copies to clipboard and shows notification
- [ ] Esc still cancels

**Verification:**
- [ ] End-to-end test with each engine configured
- [ ] Test with no config (should show letter keys as before)
- [ ] Test with missing binary (should show helpful error)

**Dependencies:** Tasks 1–4

**Files likely touched:**
- `herdr_fingers.py`
- `bin/herdr-fingers` (unchanged, no changes needed)

**Estimated scope:** S

---

### Task 6: Documentation + config template

**Description:** Update README with the new feature. Create a sample config file at `config/herdr-fingers/config.toml` in the repo for users to copy.

**Acceptance criteria:**
- [ ] README documents the `search_engine` config option with all three values
- [ ] Example config shown
- [ ] Deprecation notice for letter-key fallback (it's an escape hatch, not the primary path)

**Dependencies:** Task 5

**Files likely touched:**
- `README.md`
- New: `config/herdr-fingers/config.toml` (example)

**Estimated scope:** XS

---

## Checkpoint: After Tasks 1–2
- [ ] InquirerPy picker works standalone
- [ ] Config loader reads correctly

## Checkpoint: After Tasks 3–5
- [ ] All three engines work (where available)
- [ ] Backward compat (no config = letter keys)
- [ ] Error messages are clear when engine is missing
- [ ] End-to-end flow: extract → fuzzy pick → copy → close

## Checkpoint: Complete
- [ ] README updated
- [ ] All acceptance criteria met
- [ ] Ready for review

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| InquirerPy not in venv | S blocks | Add to pyproject.toml dependencies (optional, only if `search_engine = "inquirerpy"`) |
| fzf/skim not installed | User confusion | Clear error message naming the missing binary and how to install it |
| Picker doesn't fit in overlay pane | UX | fzf/skim use the full terminal — that's fine, the overlay pane is the full terminal. InquirerPy also fills the pane. No issue. |
| Config file path differs across herdr versions | Future break | Use well-known path; version the config format if herdr changes plugin config layout |

## Open Questions

1. **Dependency strategy for InquirerPy.** Lazy import — only import when the engine is selected.
2. **fzf flags.** No `--preview`. Clean fuzzy list only.
3. **Multi-select.** One item at a time for v1.
4. **Default engine.** Auto-detect: InquirerPy → fzf → skim. If none available, print install instructions and exit.
