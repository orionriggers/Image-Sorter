# Image Sorter — Changelog, v1.34 → v1.39

> **Note:** detailed records for this project's session journal start at v1.34.x — changes prior to that (v1.32–v1.33) aren't covered here.

## v1.39.0 — Rating & Color Labels

The headline feature: a full **rating and color-label system** for photos, videos, and PDFs, built into the grid, preview pane, filters, and context menus — not tucked away in a side panel.

- **0–5 star ratings** and **non-exclusive color labels** (a file can carry several colors at once) on every file, stored in a new standalone module (`metadata_store.py`).
- Exposed everywhere: thumbnail grid (Naviga & Timeline), enlarged preview, right-click menus, a dedicated on-image overlay in the main viewer, filtering by rating/color in Naviga, and a "Rating"/"Color" sidebar in Timeline.
- Everything stays live-synced — change a rating anywhere and it updates instantly across the grid, preview, and overlay.
- **Crop tool**: new "Original" aspect-ratio option, locking the crop box to the exact proportions of the photo being cropped.
- **"Open With..."** now genuinely remembers your chosen program instead of asking every time; a new direct Stream Deck command sends the current file straight to that editor with no dialog.
- Assorted persistence and selection-highlighting fixes.

## v1.36 – v1.37 — Stream Deck rebuilt

The physical Stream Deck integration was substantially reworked over this range:

- Deck logic extracted into its own module (`deck_core.py`), independent of the main app.
- New background **daemon** (`deck_daemon.py`) keeps the physical deck responsive even when Image Sorter itself is closed, handing control back and forth cleanly when a window opens or closes.
- Grew to **29 direct one-press commands** (rotate, delete, zoom, and more), each with a customizable icon.
- Multi-window support: commands now route to whichever Image Sorter window currently has focus.
- Replaced the old streamdeck-ui/StreamController dependency, which had become fragile across Pillow updates.
- Fixed a recurring native crash tied to keyboard-shortcut capture (uppercase vs. lowercase key symbols being treated as distinct on this hardware), plus several startup race conditions when the deck, daemon, and app windows all start close together.

## v1.35 — Workflow and UI polish

- Sidebar gained a **list view** as an alternative to the grid, and presets can now be reordered by drag-and-drop.
- Duplicate-finder gained a proper **A-vs-B comparison mode** (side-by-side preview, multi-select) for comparing two folders directly.
- Handling for unreachable/disconnected disks, plus assorted Stream Deck UI additions (extra buttons, icon folder, a status-color indicator).
- Config file switched to a human-readable JSON format.

## v1.34 — Stability pass

- Fixed several startup issues, detached the sidebar into its own panel, and added a visible error-log indicator (a small red dot) so problems are hard to miss without being intrusive.

---

**Current version:** `1.39.0` (core modules) · `metadata_store.py 1.1.0` · `deck_core.py 1.0.1` · `deck_daemon.py 1.0.0`

## 📦 Files needed for a working install

**Required — the application won't start without these:**

| File | Role |
|---|---|
| `image_sorter.py` | Main application entry point / GUI |
| `timeline.py` | Timeline view + GPS map |
| `exif_editor.py` | EXIF metadata editor |
| `disk_analyzer.py` | Disk usage analyzer (sunburst/treemap) |
| `translations.py` | IT/EN interface strings |
| `metadata_store.py` | Rating / color-label database (new in v1.38) |
| `deck_core.py` | Shared Stream Deck logic |
| `sorter_icons/` *(folder)* | Application icon, bundled at multiple sizes (window/taskbar) — verified in code as a required resource folder, not auto-generated |

**Optional, but part of the intended setup:**

| File | Role |
|---|---|
| `deck_daemon.py` | Background service that keeps a physical Stream Deck responsive while the app is closed — only needed if you use a Stream Deck |
| `installa.sh` | Installer script (dependencies, launcher, optional daemon setup) |
| `LEGGIMI.txt` / `README_en.txt` / `README.md` | User manuals and GitHub overview |

**Created automatically — do *not* need to be downloaded:**

| Path | Created by |
|---|---|
| `deck_icons/` | Auto-created on first Stream Deck use, holds your own custom per-key icons |
| `image_sorter_config.json`, `image_sorter_history.json`, `image_sorter_error.log`, `image_sorter_metadata.json` | Written on first run in the app's own folder |
| `.deck_owner.lock`, `.deck_focus.json`, `.deck_inbox_*.json` | Stream Deck coordination files, transient |
| `~/.local/share/.../` trash-transit folder | Used for undo-able deletions, outside the app folder entirely |

All of the above (required + optional) should be kept together in the same folder — several files (`deck_core.py`, `metadata_store.py`, `translations.py`, etc.) are loaded dynamically at runtime from the same directory as `image_sorter.py`, not installed as a Python package.

### Python dependencies

```
pip install Pillow piexif --user
```

- **Pillow** — required, core image handling.
- **piexif** — required for EXIF editing/writing (JPEG and WebP only); the app runs without it but EXIF-editing features report it as missing.

Optional, enable extra format support if installed (the app degrades gracefully without them):
```
pip install pillow-heif pillow-avif-plugin --user
```
- **pillow-heif** — HEIC/HEIF support
- **pillow-avif-plugin** — AVIF support

Optional, only needed for a physical Stream Deck:
```
pip install streamdeck --user
```
- Also requires **libusb** at the system level, and the **xdotool** command-line tool (not a Python package — install via your distro's package manager, e.g. `apt install xdotool`) for keyboard-shortcut simulation.

### Tested platform

Linux Mint / Ubuntu (Cinnamon, X11), Python 3.8+. Not tested on Wayland or other desktop environments.

