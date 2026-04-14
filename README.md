<div align="center">

# LSPDestroyer

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](#requirements)
[![Windows 10/11](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white)](#requirements)
[![Version 0.1.3](https://img.shields.io/badge/Version-0.1.3-111827?style=for-the-badge)](#install-as-a-package)
[![License MIT](https://img.shields.io/badge/License-MIT-16a34a?style=for-the-badge)](LICENSE)
[![Dependencies 0](https://img.shields.io/badge/Dependencies-0-0f766e?style=for-the-badge)](#requirements)
[![Built with Tkinter](https://img.shields.io/badge/UI-Tkinter-f59e0b?style=for-the-badge)](#module-summary)
[![Win32 Hooks](https://img.shields.io/badge/Backend-Win32%20Hooks-7c3aed?style=for-the-badge)](#how-it-works)
[![Status Finished](https://img.shields.io/badge/Status-Finished-16a34a?style=for-the-badge)](#development-notes)

`LSPDestroyer` is a Windows tray utility that replays the contents of a text file
into the currently focused application, one character at a time.

</div>

The app installs a global low-level keyboard hook. After you activate a file,
each printable key press is suppressed and replaced with the next character from
that file.

## Features

- Starts in the Windows system tray.
- Global hotkeys registered with `RegisterHotKey`.
- Low-level keyboard hook for character-by-character replay.
- File preview before activation, with double-click activation support.
- Context-aware preview header button: it appears when no file is active or a
  preview is waiting to be activated, then hides itself once an active file is
  already in use and no preview is pending.
- Transparent always-on-top overlay that shows the next character(s).
- Pause/resume, reset, show/hide overlay, and hide/restore UI controls.
- Editable hotkeys for `Pause / Resume` and `Show / hide next overlay`
  directly from the Settings window.
- Overlay controls for font size, opacity, and vertical padding via sliders,
  plus a color picker for text color.
- UTF-8, UTF-8 BOM, and CP1252 file loading, with replacement fallback.
- Hotkey and overlay settings persisted in `%LOCALAPPDATA%\lspdestroyer\config.json`.
- Hidden `--self-test` mode for a startup smoke test.

## Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer
- No third-party runtime dependencies

## Run From Source

```powershell
git clone https://github.com/Alpinnnn/LSPDestroyer
cd LSPDestroyer
python lspdestroyer.py
```

You can also run the package entrypoint directly:

```powershell
python -m lspdestroyer_app
```

## Install As A Package

```powershell
pip install -e .
lspdestroyer
```

## Default Hotkeys

These are the default hotkeys shown by the app.

| Action | Hotkey |
| --- | --- |
| Open or close main UI | `Ctrl+O` |
| Hide or restore UI except overlay | `Ctrl+H` |
| Open or close settings | `Ctrl+S` |
| Select file | `Ctrl+F` |
| Reset active file | `Ctrl+Delete` |
| Pause or resume typing | `Delete` |
| Show or hide overlay | `Insert` |
| Exit application | `Ctrl+Enter` |

`Pause or resume typing` and `Show or hide overlay` can be changed from the
Settings window by clicking the current hotkey value and pressing a new key.

Hotkey rules for the in-app editor:

- Character-producing keys in the typing whitelist cannot be used on their own.
- Those keys are allowed when combined with `Ctrl`.
- If you press `Ctrl` first, the UI shows `Ctrl + ...`.
- If `Ctrl` is released before a second key is chosen, the capture is canceled
  and the original hotkey is restored.
- Plain `Backspace` is blocked as a hotkey because it is reserved for moving
  back one character in the active file.

If a hotkey conflicts with another app, registration can fail and the app will
show a warning in its status text.

## How It Works

1. Start the app. It initializes in the tray and creates the main UI,
   settings window, and overlay.
2. Select a file with `Ctrl+F` or from the tray menu.
3. The file is loaded into the preview area first.
4. Activate the preview with the preview header button or by double-clicking the
   preview panel.
5. Once the preview becomes the active file, the preview button hides itself
   until you load another preview or clear back to a state with no active file.
6. Once active, printable key presses in other applications are intercepted.
7. The original key is suppressed and the next character from the file is sent
   with `SendInput`.
8. The overlay and progress indicators update as you move through the file.

### Keys That Pass Through

The hook intentionally does not replace:

- Modifier keys
- Most non-character keys such as arrows, function keys, and escape
- Ctrl-based combinations
- Injected input events
- Input while `LSPDestroyer` itself is focused

Backspace is handled specially: it sends a real backspace to the target app and
moves the current file position back by one character.

## Overlay Settings

The app configuration is stored at:

```text
%LOCALAPPDATA%\lspdestroyer\config.json
```

Overlay fields and defaults:

| Setting | Type | Default |
| --- | --- | --- |
| `font_size` | int | `12` |
| `opacity` | float | `0.92` |
| `x_position` | int | `-1` |
| `y_position` | int | `-1` |
| `padding_x` | int | `18` |
| `padding_y` | int | `10` |
| `text_color` | string | `#f8fafc` |
| `next_char_count` | int | `1` |

`x_position` and `y_position` default to `-1`, which means the overlay is
auto-centered until you drag it somewhere else.

Settings UI overview:

- `Font size`, `Opacity`, and `Vertical padding` use slider controls.
- `Text color` uses a color picker.
- `Horizontal padding` and `Total next characters` stay as direct numeric input.
- `Pause / Resume` and `Show / hide next overlay` hotkeys can be edited from
  the same Settings window.

## Project Layout

```text
.
|-- lspdestroyer.py
|-- pyproject.toml
`-- lspdestroyer_app/
    |-- __init__.py
    |-- __main__.py
    |-- app.py
    |-- cli.py
    |-- config.py
    |-- constants.py
    |-- hotkeys.py
    |-- text_utils.py
    |-- tray.py
    |-- win32.py
    `-- assets/
        |-- fonts/
        `-- icons/
```

## Module Summary

- `app.py` builds the Tkinter UI, overlay, keyboard hook, and file playback flow.
- `tray.py` owns the tray icon, tray menu, and native hotkey registration.
- `win32.py` contains the ctypes bindings used for hooks, input injection, DPI
  awareness, and acrylic blur.
- `config.py` loads and saves app configuration.
- `hotkeys.py` parses hotkey strings and defines virtual-key mappings.
- `text_utils.py` loads files and formats characters for overlay display.
- `constants.py` keeps shared UI values, paths, and file filters.

## Development Notes

There is no automated test suite in this repository right now.

For a quick smoke test, run:

```powershell
python -m lspdestroyer_app --self-test
```

To build a standalone executable:

```powershell
pip install pyinstaller
pyinstaller --noconsole --onefile --name LSPDestroyer --collect-data lspdestroyer_app lspdestroyer.py
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
