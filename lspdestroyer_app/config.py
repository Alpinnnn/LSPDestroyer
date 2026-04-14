from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path

from .constants import APP_TITLE, CONFIG_FILE_NAME


@dataclass
class HotkeyConfig:
    show_main_ui: str = "Ctrl+O"
    toggle_visibility: str = "Ctrl+H"
    open_settings: str = "Ctrl+S"
    select_file: str = "Ctrl+F"
    reset_file: str = "Ctrl+Delete"
    pause_resume: str = "Delete"
    toggle_overlay: str = "Insert"
    exit_app: str = "Ctrl+Enter"


@dataclass
class OverlayConfig:
    font_size: int = 12
    opacity: float = 0.92
    x_position: int = -1
    y_position: int = -1
    padding_x: int = 18
    padding_y: int = 10
    text_color: str = "#f8fafc"
    next_char_count: int = 1


@dataclass
class AppConfig:
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)


def get_config_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    config_dir = base / APP_TITLE
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / CONFIG_FILE_NAME


def load_config() -> AppConfig:
    path = get_config_path()
    if not path.exists():
        return AppConfig()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return AppConfig()

    hotkeys = payload.get("hotkeys", {})
    overlay = payload.get("overlay", {})
    return AppConfig(
        hotkeys=HotkeyConfig(
            show_main_ui=hotkeys.get("show_main_ui", HotkeyConfig.show_main_ui),
            toggle_visibility=hotkeys.get(
                "toggle_visibility", HotkeyConfig.toggle_visibility
            ),
            open_settings=hotkeys.get("open_settings", HotkeyConfig.open_settings),
            select_file=hotkeys.get("select_file", HotkeyConfig.select_file),
            reset_file=hotkeys.get("reset_file", HotkeyConfig.reset_file),
            pause_resume=hotkeys.get("pause_resume", HotkeyConfig.pause_resume),
            toggle_overlay=hotkeys.get(
                "toggle_overlay", HotkeyConfig.toggle_overlay
            ),
            exit_app=hotkeys.get("exit_app", HotkeyConfig.exit_app),
        ),
        overlay=OverlayConfig(
            font_size=int(overlay.get("font_size", OverlayConfig.font_size)),
            opacity=float(overlay.get("opacity", OverlayConfig.opacity)),
            x_position=int(overlay.get("x_position", OverlayConfig.x_position)),
            y_position=int(overlay.get("y_position", OverlayConfig.y_position)),
            padding_x=int(overlay.get("padding_x", OverlayConfig.padding_x)),
            padding_y=int(overlay.get("padding_y", OverlayConfig.padding_y)),
            text_color=overlay.get("text_color", OverlayConfig.text_color),
            next_char_count=int(
                overlay.get("next_char_count", OverlayConfig.next_char_count)
            ),
        ),
    )


def save_config(config: AppConfig) -> None:
    get_config_path().write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
