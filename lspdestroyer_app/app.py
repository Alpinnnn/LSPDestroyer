"""Tkinter application runtime for lspdestroyer."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import queue
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from typing import Any
import winsound

from .config import AppConfig, OverlayConfig, load_config, save_config
from .constants import *  # Shared UI palette and layout constants.
from .hotkeys import MODIFIER_KEY_CODES, OPERATIONAL_VK_CODES, VK_BACKSPACE, parse_hotkey_string
from .text_utils import describe_character, load_text_file, mix_color
from .tray import SystemTrayIcon
from .win32 import *  # Win32 bindings mirror the legacy single-file layout.

class LspDestroyerApp:
    def __init__(self, *, self_test: bool = False) -> None:
        enable_dpi_awareness()
        self.self_test = self_test
        self.config = load_config()
        self.ui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_TITLE)
        self.sidebar_icon_images: dict[str, tk.PhotoImage] = {}

        # Load Google Sans font
        self._load_custom_font()
        self._load_sidebar_icons()

        self.active_text = ""
        self.active_path: Path | None = None
        self.active_encoding = ""
        self.preview_text_value = ""
        self.preview_path: Path | None = None
        self.preview_encoding = ""
        self.preview_requires_confirmation = False
        self.current_index = 0
        self.eof_key_consumed = False
        self.ui_refresh_pending = False
        self.keyboard_hook: int | None = None
        self.suppressed_keyups: set[int] = set()
        self.exiting = False
        self.tray_icon: SystemTrayIcon | None = None
        self.native_hotkeys_registered = False
        self.hidden_by_shortcut = False
        self.restore_visibility_state = {
            "main": False,
            "settings": False,
            "overlay": False,
        }
        self.drag_origin = {"x": 0, "y": 0, "window_x": 0, "window_y": 0}
        self.overlay_drag_origin = {"x": 0, "y": 0, "window_x": 0, "window_y": 0}
        self.hotkey_last_triggered: dict[str, float] = {}
        self.active_hotkey_capture: str | None = None
        self.typing_paused = False
        self.overlay_hidden = False
        self.main_tooltip_window: tk.Toplevel | None = None
        self.main_sidebar_buttons: dict[str, dict[str, Any]] = {}
        self.preview_activate_widgets: list[tk.Widget] = []

        self.status_text = STARTUP_NOTIFICATION
        self.active_file_var = tk.StringVar(value="belum ada")
        self.preview_file_var = tk.StringVar(value="belum ada")
        self.preview_state_var = tk.StringVar(value="Belum ada preview")
        self.progress_var = tk.StringVar(value="0 / 0")
        self.status_var = tk.StringVar(value=self.status_text)
        self.overlay_label_var = tk.StringVar(value="-")

        self.overlay_vars = {
            "font_size": tk.StringVar(value=str(self.config.overlay.font_size)),
            "opacity": tk.StringVar(value=str(self.config.overlay.opacity)),
            "padding_x": tk.StringVar(value=str(self.config.overlay.padding_x)),
            "padding_y": tk.StringVar(value=str(self.config.overlay.padding_y)),
            "text_color": tk.StringVar(value=self.config.overlay.text_color),
            "next_char_count": tk.StringVar(value=str(self.config.overlay.next_char_count)),
        }

        # Hotkey actions map: action_name -> (modifiers, vk_code)
        self.hotkey_actions: dict[str, tuple[int, int]] = {}
        self._keyboard_proc_ref = LowLevelKeyboardProc(self._keyboard_proc)

        self._build_style()
        self._build_main_window()
        self._build_settings_window()
        self._build_overlay_window()
        self._refresh_hotkey_map()
        self._refresh_preview_view()
        self._refresh_main_labels()
        self._refresh_overlay()

        self._start_tray()
        self.root.after(30, self._pump_tray_messages)
        self.root.after(80, self._process_ui_queue)
        self._install_keyboard_hook()

        if self.self_test:
            self.root.after(1200, self.shutdown)

    def run(self) -> None:
        self.root.mainloop()

    def _load_custom_font(self) -> None:
        """Load Google Sans variable font using Windows GDI."""
        try:
            gdi32 = ctypes.windll.gdi32
            gdi32.AddFontResourceExW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
            gdi32.AddFontResourceExW.restype = ctypes.c_int
            FR_PRIVATE = 0x10
            result = gdi32.AddFontResourceExW(FONT_FILE, FR_PRIVATE, 0)
            if result == 0:
                pass  # Font loading failed, will fall back to system fonts
        except Exception:
            pass  # Silently ignore font loading errors

    def _load_sidebar_icons(self) -> None:
        icon_files = {
            "file": "document.png",
            "reset": "restart.png",
            "settings": "setting.png",
            "pause": "pause.png",
            "play": "play-buttton.png",
            "overlay": "hide.png",
            "exit": "close.png",
        }
        for icon_key, filename in icon_files.items():
            icon_path = ICONS_DIR / filename
            if not icon_path.is_file():
                continue
            try:
                image = tk.PhotoImage(file=str(icon_path))
                scale = max(1, image.width() // MAIN_ICON_CANVAS_SIZE)
                if scale > 1:
                    image = image.subsample(scale, scale)
                self.sidebar_icon_images[icon_key] = image
            except tk.TclError:
                continue

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=FONT_BODY)
        style.configure(
            "Modern.TCombobox",
            arrowsize=14,
            padding=8,
            fieldbackground=CARD_BACKGROUND_ALT,
            background=CARD_BACKGROUND_ALT,
            foreground=TEXT_PRIMARY,
            bordercolor=CARD_BORDER,
            lightcolor=CARD_BACKGROUND_ALT,
            darkcolor=CARD_BACKGROUND_ALT,
            arrowcolor=TEXT_PRIMARY,
        )
        style.map(
            "Modern.TCombobox",
            fieldbackground=[("readonly", CARD_BACKGROUND_ALT)],
            selectbackground=[("readonly", BUTTON_PRIMARY_ACTIVE)],
            selectforeground=[("readonly", TEXT_PRIMARY)],
            foreground=[("readonly", TEXT_PRIMARY)],
        )
        style.configure(
            "Glass.Vertical.TScrollbar",
            gripcount=0,
            background=SCROLLBAR_THUMB,
            darkcolor=SCROLLBAR_THUMB,
            lightcolor=SCROLLBAR_THUMB,
            troughcolor=SCROLLBAR_TROUGH,
            bordercolor=SCROLLBAR_TROUGH,
            arrowcolor=TEXT_MUTED,
        )
        style.configure(
            "Glass.Horizontal.TScrollbar",
            gripcount=0,
            background=SCROLLBAR_THUMB,
            darkcolor=SCROLLBAR_THUMB,
            lightcolor=SCROLLBAR_THUMB,
            troughcolor=SCROLLBAR_TROUGH,
            bordercolor=SCROLLBAR_TROUGH,
            arrowcolor=TEXT_MUTED,
        )

    def _configure_borderless_window(
        self,
        window: tk.Toplevel,
        *,
        geometry: str,
        minsize: tuple[int, int],
        alpha: float,
        topmost: bool = False,
        resizable: bool = False,
    ) -> None:
        window.withdraw()
        window.overrideredirect(True)
        window.geometry(geometry)
        window.minsize(*minsize)
        window.configure(bg=WINDOW_BACKGROUND, highlightthickness=0, bd=0)
        window.attributes("-alpha", alpha)
        self._set_window_topmost(window, topmost)
        if resizable:
            self._bind_window_resize(window, minsize)

    def _create_window_shell(
        self,
        window: tk.Toplevel,
        *,
        padding: int,
        inner_padding: int,
        palette: tuple[str, str, str],
    ) -> tuple[tk.Canvas, tk.Frame, tk.Frame]:
        canvas = tk.Canvas(
            window,
            highlightthickness=0,
            bd=0,
            relief="flat",
            bg=WINDOW_BACKGROUND,
        )
        canvas.pack(fill="both", expand=True)

        surface = tk.Frame(
            canvas,
            bg=SURFACE_BACKGROUND,
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            highlightcolor=CARD_BORDER,
            bd=0,
        )
        content = tk.Frame(surface, bg=SURFACE_BACKGROUND, bd=0)
        content.pack(fill="both", expand=True, padx=inner_padding, pady=inner_padding)
        surface_id = canvas.create_window(padding, padding, anchor="nw", window=surface)
        canvas.bind(
            "<Configure>",
            lambda event, canv=canvas, item=surface_id, pad=padding, colors=palette: self._layout_window_shell(
                event, canv, item, pad, colors
            ),
        )
        return canvas, surface, content

    def _layout_window_shell(
        self,
        event: tk.Event,
        canvas: tk.Canvas,
        surface_id: int,
        padding: int,
        palette: tuple[str, str, str],
    ) -> None:
        width = max(1, event.width)
        height = max(1, event.height)
        if getattr(canvas, "_last_gradient_size", None) != (width, height):
            canvas._last_gradient_size = (width, height)  # type: ignore[attr-defined]
            self._draw_gradient_backdrop(canvas, width, height, palette)

        canvas.coords(surface_id, padding, padding)
        canvas.itemconfigure(
            surface_id,
            width=max(320, width - padding * 2),
            height=max(180, height - padding * 2),
        )

    def _draw_gradient_backdrop(
        self,
        canvas: tk.Canvas,
        width: int,
        height: int,
        palette: tuple[str, str, str],
    ) -> None:
        canvas.delete("gradient")
        segments = len(palette) - 1
        for index in range(height):
            ratio = 0.0 if height <= 1 else index / (height - 1)
            scaled = ratio * segments
            segment_index = min(int(scaled), segments - 1)
            local_ratio = scaled - segment_index
            color = mix_color(
                palette[segment_index], palette[segment_index + 1], local_ratio
            )
            canvas.create_line(0, index, width, index, fill=color, tags="gradient")

        canvas.create_oval(
            int(width * 0.56),
            int(-height * 0.18),
            int(width * 1.18),
            int(height * 0.42),
            fill=mix_color(GRADIENT_PURPLE, GRADIENT_BLUE, 0.35),
            outline="",
            stipple="gray50",
            tags="gradient",
        )
        canvas.create_oval(
            int(-width * 0.2),
            int(height * 0.48),
            int(width * 0.38),
            int(height * 1.16),
            fill=mix_color(GRADIENT_BLUE, GRADIENT_GREEN, 0.55),
            outline="",
            stipple="gray50",
            tags="gradient",
        )
        canvas.create_line(
            28,
            22,
            max(28, width - 28),
            22,
            fill=mix_color("#ffffff", GRADIENT_BLUE, 0.55),
            width=1,
            tags="gradient",
        )
        canvas.tag_lower("gradient")

    def _create_card(
        self,
        parent: tk.Widget,
        *,
        title: str,
        subtitle: str = "",
        alternate: bool = False,
    ) -> tuple[tk.Frame, tk.Frame]:
        background = CARD_BACKGROUND_ALT if alternate else CARD_BACKGROUND
        card = tk.Frame(
            parent,
            bg=background,
            highlightthickness=1,
            highlightbackground=mix_color(CARD_BORDER, background, 0.7),
            bd=0,
        )
        header = tk.Frame(card, bg=background)
        header.pack(fill="x", padx=18, pady=(16, 10))
        tk.Label(
            header,
            text=title,
            bg=background,
            fg=TEXT_PRIMARY,
            font=FONT_CARD_TITLE,
            anchor="w",
        ).pack(anchor="w")
        if subtitle:
            tk.Label(
                header,
                text=subtitle,
                bg=background,
                fg=TEXT_SUBTLE,
                font=FONT_SUBTITLE,
                anchor="w",
            ).pack(anchor="w", pady=(4, 0))

        body = tk.Frame(card, bg=background, bd=0)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        return card, body

    def _create_action_button(
        self, parent: tk.Widget, *, text: str, command: Any, accent: bool = False
    ) -> tk.Button:
        background = BUTTON_ACCENT if accent else BUTTON_PRIMARY
        active_background = BUTTON_ACCENT_ACTIVE if accent else BUTTON_PRIMARY_ACTIVE
        return tk.Button(
            parent,
            text=text,
            command=command,
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=background,
            activebackground=active_background,
            fg=TEXT_PRIMARY,
            activeforeground=TEXT_PRIMARY,
            font=FONT_BUTTON,
            padx=16,
            pady=10,
            cursor="hand2",
            disabledforeground=TEXT_SUBTLE,
        )

    def _create_info_value(
        self, parent: tk.Widget, *, label: str, variable: tk.StringVar
    ) -> None:
        block = tk.Frame(parent, bg=parent.cget("bg"))
        block.pack(fill="x", pady=(0, 10))
        tk.Label(
            block,
            text=label,
            bg=parent.cget("bg"),
            fg=TEXT_SUBTLE,
            font=FONT_CAPTION,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            block,
            textvariable=variable,
            bg=parent.cget("bg"),
            fg=TEXT_PRIMARY,
            font=FONT_BODY,
            justify="left",
            wraplength=780,
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

    def _create_shortcut_chip(self, parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=CARD_BACKGROUND_ALT,
            fg=TEXT_PRIMARY,
            font=FONT_CAPTION,
            padx=10,
            pady=4,
        ).pack(side="left", padx=(0, 8))

    def _style_entry_widget(self, widget: tk.Entry) -> None:
        widget.configure(
            bg=CARD_BACKGROUND_ALT,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=mix_color(CARD_BORDER, CARD_BACKGROUND_ALT, 0.72),
            highlightcolor=CARD_BORDER,
            font=FONT_BODY,
        )

    def _draw_rounded_rectangle(
        self,
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        radius: int,
        **kwargs: Any,
    ) -> int:
        radius = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
        if radius == 0:
            return canvas.create_rectangle(x1, y1, x2, y2, **kwargs)

        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        return canvas.create_polygon(points, smooth=True, splinesteps=36, **kwargs)

    def _show_main_tooltip(self, widget: tk.Widget, text: str) -> None:
        if not text or not widget.winfo_exists():
            return

        self._hide_main_tooltip()
        tooltip = tk.Toplevel(self.root)
        tooltip.overrideredirect(True)
        tooltip.attributes("-topmost", True)
        tooltip.configure(bg=MAIN_TOOLTIP_BACKGROUND, highlightthickness=0, bd=0)
        tk.Label(
            tooltip,
            text=text,
            bg=MAIN_TOOLTIP_BACKGROUND,
            fg=MAIN_TOOLTIP_FOREGROUND,
            font=FONT_TOOLTIP,
            padx=10,
            pady=6,
            justify="left",
            wraplength=260,
        ).pack()
        tooltip.update_idletasks()

        x_position = widget.winfo_rootx() + widget.winfo_width() + 10
        y_position = widget.winfo_rooty() + max(
            0, (widget.winfo_height() - tooltip.winfo_reqheight()) // 2
        )
        screen_width = widget.winfo_screenwidth()
        screen_height = widget.winfo_screenheight()
        x_position = min(x_position, screen_width - tooltip.winfo_reqwidth() - 12)
        y_position = min(y_position, screen_height - tooltip.winfo_reqheight() - 12)
        tooltip.geometry(f"+{max(12, x_position)}+{max(12, y_position)}")
        self.main_tooltip_window = tooltip

    def _hide_main_tooltip(self) -> None:
        if self.main_tooltip_window and self.main_tooltip_window.winfo_exists():
            self.main_tooltip_window.destroy()
        self.main_tooltip_window = None

    def _create_sidebar_button(
        self,
        parent: tk.Widget,
        *,
        key: str,
        icon_name: str,
        command: Any,
        tooltip_getter: Any,
        secondary_command: Any | None = None,
    ) -> tk.Frame:
        button_frame = tk.Frame(
            parent,
            width=MAIN_ICON_BUTTON_SIZE,
            height=MAIN_ICON_BUTTON_SIZE,
            bg=MAIN_WINDOW_BACKGROUND,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        button_frame.pack(anchor="center", pady=6)
        button_frame.pack_propagate(False)
        button_frame._drag_exempt = True  # type: ignore[attr-defined]

        icon_label = tk.Label(
            button_frame,
            bg=MAIN_WINDOW_BACKGROUND,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            compound="center",
            font=FONT_META_LABEL,
        )
        icon_label.place(relx=0.5, rely=0.5, anchor="center")
        icon_label._drag_exempt = True  # type: ignore[attr-defined]

        self.main_sidebar_buttons[key] = {
            "frame": button_frame,
            "icon_label": icon_label,
            "icon_name": icon_name,
            "command": command,
            "secondary_command": secondary_command,
            "tooltip_getter": tooltip_getter,
            "hovered": False,
            "active": False,
            "muted": False,
        }

        for widget in (button_frame, icon_label):
            widget.bind(
                "<Enter>",
                lambda _event, button_key=key: self._on_sidebar_button_enter(
                    button_key
                ),
                add="+",
            )
            widget.bind(
                "<Leave>",
                lambda _event, button_key=key: self._on_sidebar_button_leave(
                    button_key
                ),
                add="+",
            )
            widget.bind(
                "<Button-1>",
                lambda _event, button_key=key: self._invoke_sidebar_button(
                    button_key
                ),
                add="+",
            )
            widget.bind(
                "<Button-3>",
                lambda _event, button_key=key: self._invoke_sidebar_button(
                    button_key, secondary=True
                ),
                add="+",
            )

        self._sync_sidebar_button_visual(key)
        return button_frame

    def _on_sidebar_button_enter(self, button_key: str) -> None:
        button = self.main_sidebar_buttons.get(button_key)
        if not button:
            return

        button["hovered"] = True
        self._sync_sidebar_button_visual(button_key)
        self._show_main_tooltip(button["frame"], button["tooltip_getter"]())

    def _on_sidebar_button_leave(self, button_key: str) -> None:
        button = self.main_sidebar_buttons.get(button_key)
        if not button:
            return

        button["hovered"] = False
        self._sync_sidebar_button_visual(button_key)
        self._hide_main_tooltip()

    def _invoke_sidebar_button(self, button_key: str, secondary: bool = False) -> str:
        button = self.main_sidebar_buttons.get(button_key)
        if not button:
            return "break"

        self._hide_main_tooltip()
        command = button["command"]
        if secondary and button.get("secondary_command") is not None:
            command = button["secondary_command"]
        command()
        return "break"

    def _set_sidebar_button_state(
        self, button_key: str, *, active: bool = False, muted: bool = False
    ) -> None:
        button = self.main_sidebar_buttons.get(button_key)
        if not button:
            return

        button["active"] = active
        button["muted"] = muted
        self._sync_sidebar_button_visual(button_key)

    def _sync_sidebar_button_visual(self, button_key: str) -> None:
        button = self.main_sidebar_buttons.get(button_key)
        if not button:
            return

        background = MAIN_WINDOW_BACKGROUND
        if button["active"]:
            background = MAIN_BUTTON_ACTIVE
        elif button["hovered"]:
            background = MAIN_BUTTON_HOVER

        foreground = MAIN_TEXT_PRIMARY
        if button["muted"]:
            foreground = MAIN_TEXT_SUBTLE

        icon_image = self._get_sidebar_icon_image(button_key)
        button["frame"].configure(bg=background)
        button["icon_label"].configure(
            bg=background,
            fg=foreground,
            image=icon_image,
            text="" if icon_image else button["icon_name"][:1].upper(),
        )

    def _get_sidebar_icon_image(self, button_key: str) -> tk.PhotoImage | str:
        icon_key = button_key
        if button_key == "pause":
            icon_key = "play" if self.typing_paused else "pause"
        return self.sidebar_icon_images.get(icon_key, "")

    def _truncate_text_to_width(
        self, text: str, font: tkfont.Font, max_width: int
    ) -> str:
        if max_width <= 0 or font.measure(text) <= max_width:
            return text

        ellipsis = "..."
        if font.measure(ellipsis) >= max_width:
            return ellipsis

        left_length = max(1, len(text) // 2)
        right_length = max(1, len(text) // 3)
        candidate = text
        while left_length > 0 and right_length > 0:
            candidate = f"{text[:left_length]}{ellipsis}{text[-right_length:]}"
            if font.measure(candidate) <= max_width:
                return candidate
            if left_length >= right_length:
                left_length -= 1
            else:
                right_length -= 1
        return ellipsis

    def _refresh_active_file_display(self, max_width: int | None = None) -> None:
        full_text = str(self.active_path) if self.active_path else "belum ada"
        if not hasattr(self, "main_active_value_label"):
            self.active_file_var.set(full_text)
            return

        available_width = max_width or getattr(self, "main_active_label_max_width", 240)
        font = tkfont.Font(font=self.main_active_value_label.cget("font"))
        self.active_file_var.set(
            self._truncate_text_to_width(full_text, font, max(80, available_width))
        )

    def _layout_main_window_shell(self, event: tk.Event) -> None:
        width = max(1, event.width)
        height = max(1, event.height)
        self.main_canvas.delete("main-shell")
        self._draw_rounded_rectangle(
            self.main_canvas,
            0,
            0,
            width,
            height,
            MAIN_CORNER_RADIUS,
            fill=MAIN_WINDOW_BACKGROUND,
            outline="",
            tags="main-shell",
        )
        self.main_canvas.create_line(
            MAIN_SIDEBAR_WIDTH,
            0,
            MAIN_SIDEBAR_WIDTH,
            height,
            fill=MAIN_DIVIDER,
            width=1,
            tags="main-shell",
        )
        self.main_canvas.create_line(
            0,
            MAIN_HEADER_HEIGHT,
            width,
            MAIN_HEADER_HEIGHT,
            fill=MAIN_DIVIDER,
            width=1,
            tags="main-shell",
        )
        self.main_canvas.tag_lower("main-shell")

        content_width = max(320, width - MAIN_SIDEBAR_WIDTH - (MAIN_CONTENT_GAP * 2))
        content_height = max(220, height - MAIN_HEADER_HEIGHT - (MAIN_CONTENT_GAP * 2))

        self.main_canvas.coords(self.main_brand_window, MAIN_SIDEBAR_WIDTH, 0)
        self.main_canvas.itemconfigure(
            self.main_brand_window,
            width=max(260, width - MAIN_SIDEBAR_WIDTH),
            height=MAIN_HEADER_HEIGHT,
        )

        self.main_canvas.coords(self.main_sidebar_window, 0, MAIN_HEADER_HEIGHT + 10)
        self.main_canvas.itemconfigure(
            self.main_sidebar_window,
            width=MAIN_SIDEBAR_WIDTH,
            height=max(200, height - MAIN_HEADER_HEIGHT - 16),
        )

        self.main_canvas.coords(
            self.main_content_window,
            MAIN_SIDEBAR_WIDTH + MAIN_CONTENT_GAP,
            MAIN_HEADER_HEIGHT + MAIN_CONTENT_GAP,
        )
        self.main_canvas.itemconfigure(
            self.main_content_window, width=content_width, height=content_height
        )

        if hasattr(self, "main_progress_block") and hasattr(
            self, "main_active_value_label"
        ):
            progress_width = self.main_progress_block.winfo_reqwidth()
            self.main_active_label_max_width = max(
                180,
                content_width - progress_width - 28 - 40,
            )
            self._refresh_active_file_display(self.main_active_label_max_width)

    def _handle_primary_file_action(self) -> None:
        if self.preview_requires_confirmation and self.preview_text_value:
            self.confirm_preview_file()
            return
        self.select_file_via_dialog_from_ui()

    def _activate_preview_from_ui(self, _event: tk.Event | None = None) -> str | None:
        if not self.preview_requires_confirmation:
            return None
        self.confirm_preview_file()
        return "break"

    def _sync_preview_interaction_state(self) -> None:
        if not self.preview_activate_widgets:
            return

        cursor = "hand2" if self.preview_requires_confirmation else "arrow"
        title_color = MAIN_TEXT_PRIMARY if self.preview_text_value else MAIN_TEXT_SUBTLE
        for widget in self.preview_activate_widgets:
            widget.configure(cursor=cursor)
        self.preview_title_label.configure(fg=title_color)
        if hasattr(self, "preview_select_button"):
            button_state = "normal" if self.preview_requires_confirmation else "disabled"
            self.preview_select_button.configure(state=button_state)

    def _get_file_button_tooltip(self) -> str:
        if self.preview_requires_confirmation:
            return (
                "Klik kiri untuk pakai preview. "
                f"Klik kanan atau {self.config.hotkeys.select_file} untuk pilih file lain."
            )
        return f"Pilih file ({self.config.hotkeys.select_file})"

    def _get_reset_button_tooltip(self) -> str:
        return f"Reset posisi karakter ({self.config.hotkeys.reset_file})"

    def _get_settings_button_tooltip(self) -> str:
        return f"Buka settings ({self.config.hotkeys.open_settings})"

    def _get_pause_button_tooltip(self) -> str:
        action = "Resume typing" if self.typing_paused else "Pause typing"
        return f"{action} ({self.config.hotkeys.pause_resume})"

    def _get_overlay_button_tooltip(self) -> str:
        action = "Tampilkan overlay" if self.overlay_hidden else "Sembunyikan overlay"
        return f"{action} ({self.config.hotkeys.toggle_overlay})"

    def _get_exit_button_tooltip(self) -> str:
        return f"Keluar dari aplikasi ({self.config.hotkeys.exit_app})"

    def _layout_scroll_canvas(
        self,
        canvas: tk.Canvas,
        frame_window: int,
        content: tk.Frame,
    ) -> None:
        try:
            width = max(1, canvas.winfo_width())
            canvas.itemconfigure(frame_window, width=width)
            canvas.configure(scrollregion=canvas.bbox("all"))
        except tk.TclError:
            return

    def _scroll_canvas_with_mousewheel(self, canvas: tk.Canvas, event: tk.Event) -> str:
        if not canvas.winfo_exists():
            return "break"

        delta = 0
        if getattr(event, "delta", 0):
            delta = -int(event.delta / 120)
        elif getattr(event, "num", 0) == 4:
            delta = -1
        elif getattr(event, "num", 0) == 5:
            delta = 1

        if delta:
            canvas.yview_scroll(delta, "units")
        return "break"

    def _bind_canvas_mousewheel(self, canvas: tk.Canvas, *widgets: tk.Widget) -> None:
        seen_widgets: set[int] = set()
        excluded_widgets = (tk.Text, ttk.Scrollbar, tk.Scrollbar)

        def bind_widget(widget: tk.Widget) -> None:
            widget_id = id(widget)
            if widget_id in seen_widgets:
                return
            seen_widgets.add(widget_id)

            if isinstance(widget, excluded_widgets):
                return

            widget.bind(
                "<MouseWheel>",
                lambda event, canv=canvas: self._scroll_canvas_with_mousewheel(
                    canv, event
                ),
                add="+",
            )
            widget.bind(
                "<Button-4>",
                lambda event, canv=canvas: self._scroll_canvas_with_mousewheel(
                    canv, event
                ),
                add="+",
            )
            widget.bind(
                "<Button-5>",
                lambda event, canv=canvas: self._scroll_canvas_with_mousewheel(
                    canv, event
                ),
                add="+",
            )

            for child in widget.winfo_children():
                bind_widget(child)

        for widget in widgets:
            bind_widget(widget)

    def _toggle_pause_resume(self) -> None:
        self.typing_paused = not self.typing_paused
        self.set_status("Paused." if self.typing_paused else "Resumed.")
        self._refresh_button_labels()
        self._refresh_overlay()

    def _toggle_overlay_visibility(self) -> None:
        self.overlay_hidden = not self.overlay_hidden
        self.set_status("Overlay hidden." if self.overlay_hidden else "Overlay shown.")
        self._refresh_button_labels()
        self._refresh_overlay()

    def _start_overlay_drag(self, event: tk.Event) -> None:
        """Start overlay drag on right-click."""
        self.overlay_drag_origin["x"] = event.x_root
        self.overlay_drag_origin["y"] = event.y_root
        self.overlay_drag_origin["window_x"] = self.config.overlay.x_position
        self.overlay_drag_origin["window_y"] = self.config.overlay.y_position
        if self.overlay_drag_origin["window_x"] < 0 or self.overlay_drag_origin["window_y"] < 0:
            self.overlay_window.update_idletasks()
            self.overlay_drag_origin["window_x"] = self.overlay_window.winfo_x()
            self.overlay_drag_origin["window_y"] = self.overlay_window.winfo_y()

    def _drag_overlay(self, event: tk.Event) -> None:
        delta_x = event.x_root - self.overlay_drag_origin["x"]
        delta_y = event.y_root - self.overlay_drag_origin["y"]
        self.config.overlay.x_position = self.overlay_drag_origin["window_x"] + delta_x
        self.config.overlay.y_position = self.overlay_drag_origin["window_y"] + delta_y
        self._position_overlay()

    def _sync_overlay_handle(self) -> None:
        if not hasattr(self, "overlay_handle_window"):
            return

        if not self._should_show_overlay():
            self.overlay_handle_window.withdraw()
            return

        self.overlay_window.update_idletasks()
        handle_width = max(72, self.overlay_window.winfo_width())
        handle_x = self.overlay_window.winfo_x()
        handle_y = max(0, self.overlay_window.winfo_y() - 16)
        self.overlay_handle_window.geometry(f"{handle_width}x14+{handle_x}+{handle_y}")
        self.overlay_handle_window.deiconify()
        self._set_window_topmost(self.overlay_handle_window, True)
        self.overlay_handle_window.lift()

    def _bind_window_drag(self, window: tk.Toplevel, *widgets: tk.Widget) -> None:
        interactive_widgets = (
            tk.Text,
            tk.Entry,
            tk.Button,
            tk.Checkbutton,
            tk.Listbox,
            tk.Menubutton,
            tk.Radiobutton,
            tk.Scale,
            tk.Spinbox,
            tk.Scrollbar,
            ttk.Entry,
            ttk.Combobox,
            ttk.Button,
            ttk.Checkbutton,
            ttk.Radiobutton,
            ttk.Scrollbar,
        )
        seen_widgets: set[int] = set()

        def bind_widget(widget: tk.Widget) -> None:
            widget_id = id(widget)
            if widget_id in seen_widgets:
                return
            seen_widgets.add(widget_id)

            if isinstance(widget, interactive_widgets) or getattr(
                widget, "_drag_exempt", False
            ):
                return

            widget.bind(
                "<ButtonPress-1>",
                lambda event, win=window: self._start_window_drag(event, win),
                add="+",
            )
            widget.bind(
                "<B1-Motion>",
                lambda event, win=window: self._drag_window(event, win),
                add="+",
            )

            for child in widget.winfo_children():
                bind_widget(child)

        for widget in widgets:
            bind_widget(widget)

    def _start_window_drag(self, event: tk.Event, window: tk.Toplevel) -> None:
        self.drag_origin["x"] = event.x_root
        self.drag_origin["y"] = event.y_root
        self.drag_origin["window_x"] = window.winfo_x()
        self.drag_origin["window_y"] = window.winfo_y()

    def _drag_window(self, event: tk.Event, window: tk.Toplevel) -> None:
        delta_x = event.x_root - self.drag_origin["x"]
        delta_y = event.y_root - self.drag_origin["y"]
        window.geometry(
            f"+{self.drag_origin['window_x'] + delta_x}+{self.drag_origin['window_y'] + delta_y}"
        )

    def _bind_window_resize(
        self, window: tk.Toplevel, minsize: tuple[int, int]
    ) -> None:
        """Bind edge-drag resizing to a borderless window."""
        resize_state: dict[str, Any] = {
            "edge": "",
            "start_x": 0,
            "start_y": 0,
            "start_w": 0,
            "start_h": 0,
            "start_wx": 0,
            "start_wy": 0,
        }
        # Only allow resize when the event is on these widget types
        # (the window background / gradient canvas / surface frame).
        # This prevents scrollbar and action-button areas from
        # triggering accidental resizes.
        resize_allowed_types = (tk.Toplevel, tk.Canvas, tk.Frame)

        def _detect_edge(event: tk.Event) -> str:
            # Map event coords to window-relative position
            try:
                wx = event.widget.winfo_rootx() - window.winfo_rootx() + event.x
                wy = event.widget.winfo_rooty() - window.winfo_rooty() + event.y
            except tk.TclError:
                return ""
            w = window.winfo_width()
            h = window.winfo_height()
            edge = ""
            if wy < RESIZE_EDGE_WIDTH:
                edge += "n"
            elif wy > h - RESIZE_EDGE_WIDTH:
                edge += "s"
            if wx < RESIZE_EDGE_WIDTH:
                edge += "w"
            elif wx > w - RESIZE_EDGE_WIDTH:
                edge += "e"
            return edge

        def _update_cursor(event: tk.Event) -> None:
            if not isinstance(event.widget, resize_allowed_types):
                return
            edge = _detect_edge(event)
            cursors = {
                "n": "top_side",
                "s": "bottom_side",
                "e": "right_side",
                "w": "left_side",
                "ne": "top_right_corner",
                "nw": "top_left_corner",
                "se": "bottom_right_corner",
                "sw": "bottom_left_corner",
            }
            cursor = cursors.get(edge, "")
            try:
                window.configure(cursor=cursor)
            except tk.TclError:
                pass

        def _start_resize(event: tk.Event) -> None:
            if not isinstance(event.widget, resize_allowed_types):
                return
            edge = _detect_edge(event)
            if not edge:
                return
            resize_state["edge"] = edge
            resize_state["start_x"] = event.x_root
            resize_state["start_y"] = event.y_root
            resize_state["start_w"] = window.winfo_width()
            resize_state["start_h"] = window.winfo_height()
            resize_state["start_wx"] = window.winfo_x()
            resize_state["start_wy"] = window.winfo_y()

        def _do_resize(event: tk.Event) -> None:
            edge = resize_state["edge"]
            if not edge:
                return
            dx = event.x_root - resize_state["start_x"]
            dy = event.y_root - resize_state["start_y"]
            new_x = resize_state["start_wx"]
            new_y = resize_state["start_wy"]
            new_w = resize_state["start_w"]
            new_h = resize_state["start_h"]

            if "e" in edge:
                new_w = max(minsize[0], resize_state["start_w"] + dx)
            if "s" in edge:
                new_h = max(minsize[1], resize_state["start_h"] + dy)
            if "w" in edge:
                candidate_w = resize_state["start_w"] - dx
                if candidate_w >= minsize[0]:
                    new_w = candidate_w
                    new_x = resize_state["start_wx"] + dx
            if "n" in edge:
                candidate_h = resize_state["start_h"] - dy
                if candidate_h >= minsize[1]:
                    new_h = candidate_h
                    new_y = resize_state["start_wy"] + dy

            window.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")

        def _stop_resize(_event: tk.Event) -> None:
            resize_state["edge"] = ""
            try:
                window.configure(cursor="")
            except tk.TclError:
                pass

        window.bind("<Motion>", _update_cursor, add="+")
        window.bind("<ButtonPress-1>", _start_resize, add="+")
        window.bind("<B1-Motion>", _do_resize, add="+")
        window.bind("<ButtonRelease-1>", _stop_resize, add="+")

    def _apply_window_blur(
        self,
        window: tk.Toplevel,
        *,
        opacity: float,
        tint_color: str,
        click_through: bool = False,
    ) -> None:
        try:
            hwnd = window.winfo_id()
        except tk.TclError:
            return

        style = GetWindowLongPtr(hwnd, GWL_EXSTYLE) | WS_EX_TOOLWINDOW
        if click_through:
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
        SetWindowLongPtr(hwnd, GWL_EXSTYLE, style)
        enable_window_blur(hwnd, tint_color=tint_color)
        try:
            window.attributes("-alpha", opacity)
        except tk.TclError:
            pass

    def _build_main_window(self) -> None:
        self.main_window = tk.Toplevel(self.root)
        self.main_window.title(APP_TITLE)
        self._configure_borderless_window(
            self.main_window,
            geometry=DEFAULT_MAIN_GEOMETRY,
            minsize=MAIN_MIN_SIZE,
            alpha=WINDOW_ALPHA,
            topmost=True,
            resizable=True,
        )
        self.main_window.protocol("WM_DELETE_WINDOW", self.hide_main_window)
        self.main_window.configure(bg=MAIN_TRANSPARENT_COLOR)
        self.main_window.attributes("-transparentcolor", MAIN_TRANSPARENT_COLOR)

        self.main_canvas = tk.Canvas(
            self.main_window,
            highlightthickness=0,
            bd=0,
            relief="flat",
            bg=MAIN_TRANSPARENT_COLOR,
        )
        self.main_canvas.pack(fill="both", expand=True)

        self.main_brand_frame = tk.Frame(
            self.main_canvas,
            bg=MAIN_WINDOW_BACKGROUND,
            bd=0,
            highlightthickness=0,
        )
        self.main_brand_frame.pack_propagate(False)
        brand_row = tk.Frame(self.main_brand_frame, bg=MAIN_WINDOW_BACKGROUND, bd=0)
        brand_row.place(
            x=MAIN_BRAND_LEFT_PADDING, rely=0.5, y=1, anchor="w"
        )
        title_label = tk.Label(
            brand_row,
            text="LSPDestroyer",
            bg=MAIN_WINDOW_BACKGROUND,
            fg=MAIN_TEXT_PRIMARY,
            font=FONT_BRAND_TITLE,
            anchor="w",
        )
        title_label.pack(side="left", anchor="s")
        brand_tag = tk.Label(
            brand_row,
            text="By Euphyfve",
            bg=MAIN_WINDOW_BACKGROUND,
            fg=MAIN_TEXT_PRIMARY,
            font=FONT_BRAND_SUBTITLE,
            anchor="w",
        )
        brand_tag.pack(side="left", anchor="s", padx=(8, 0), pady=(8, 0))
        self.main_brand_window = self.main_canvas.create_window(
            0, 0, anchor="nw", window=self.main_brand_frame
        )

        self.main_sidebar_frame = tk.Frame(
            self.main_canvas,
            bg=MAIN_WINDOW_BACKGROUND,
            bd=0,
            highlightthickness=0,
        )
        self.main_sidebar_window = self.main_canvas.create_window(
            0, 0, anchor="nw", window=self.main_sidebar_frame
        )

        self._create_sidebar_button(
            self.main_sidebar_frame,
            key="file",
            icon_name="file",
            command=self._handle_primary_file_action,
            tooltip_getter=self._get_file_button_tooltip,
            secondary_command=self.select_file_via_dialog_from_ui,
        )
        self._create_sidebar_button(
            self.main_sidebar_frame,
            key="reset",
            icon_name="reset",
            command=self.reset_active_file,
            tooltip_getter=self._get_reset_button_tooltip,
        )
        self._create_sidebar_button(
            self.main_sidebar_frame,
            key="settings",
            icon_name="settings",
            command=self.toggle_settings_window,
            tooltip_getter=self._get_settings_button_tooltip,
        )
        self._create_sidebar_button(
            self.main_sidebar_frame,
            key="pause",
            icon_name="pause",
            command=self._toggle_pause_resume,
            tooltip_getter=self._get_pause_button_tooltip,
        )
        self._create_sidebar_button(
            self.main_sidebar_frame,
            key="overlay",
            icon_name="overlay",
            command=self._toggle_overlay_visibility,
            tooltip_getter=self._get_overlay_button_tooltip,
        )
        self._create_sidebar_button(
            self.main_sidebar_frame,
            key="exit",
            icon_name="exit",
            command=self.shutdown,
            tooltip_getter=self._get_exit_button_tooltip,
        )

        self.main_content = tk.Frame(
            self.main_canvas,
            bg=MAIN_WINDOW_BACKGROUND,
            bd=0,
            highlightthickness=0,
        )
        self.main_content.columnconfigure(0, weight=1)
        self.main_content.rowconfigure(1, weight=1)
        self.main_content_window = self.main_canvas.create_window(
            0, 0, anchor="nw", window=self.main_content
        )

        info_row = tk.Frame(self.main_content, bg=MAIN_WINDOW_BACKGROUND, bd=0)
        info_row.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        info_row.columnconfigure(0, weight=0)
        info_row.columnconfigure(1, weight=0)
        info_row.columnconfigure(2, weight=1)

        self.main_active_block = tk.Frame(info_row, bg=MAIN_WINDOW_BACKGROUND, bd=0)
        self.main_active_block.grid(row=0, column=0, sticky="w")
        tk.Label(
            self.main_active_block,
            text="Active File",
            bg=MAIN_WINDOW_BACKGROUND,
            fg=MAIN_TEXT_PRIMARY,
            font=FONT_META_LABEL,
            anchor="w",
        ).pack(anchor="w")
        self.main_active_value_label = tk.Label(
            self.main_active_block,
            textvariable=self.active_file_var,
            bg=MAIN_WINDOW_BACKGROUND,
            fg=MAIN_TEXT_MUTED,
            font=FONT_META_VALUE,
            justify="left",
            anchor="w",
        )
        self.main_active_value_label.pack(anchor="w", pady=(0, 0))

        self.main_progress_block = tk.Frame(info_row, bg=MAIN_WINDOW_BACKGROUND, bd=0)
        self.main_progress_block.grid(
            row=0, column=1, sticky="w", padx=(28, 0)
        )
        tk.Label(
            self.main_progress_block,
            text="Progress",
            bg=MAIN_WINDOW_BACKGROUND,
            fg=MAIN_TEXT_PRIMARY,
            font=FONT_META_LABEL,
            anchor="w",
        ).pack(anchor="w")
        self.main_progress_value_label = tk.Label(
            self.main_progress_block,
            textvariable=self.progress_var,
            bg=MAIN_WINDOW_BACKGROUND,
            fg=MAIN_TEXT_MUTED,
            font=FONT_META_VALUE,
            anchor="w",
        )
        self.main_progress_value_label.pack(anchor="w", pady=(0, 0))

        self.preview_panel = tk.Frame(
            self.main_content,
            bg=MAIN_PANEL_BACKGROUND,
            bd=0,
            highlightthickness=0,
        )
        self.preview_panel.grid(row=1, column=0, sticky="nsew")
        self.preview_panel.columnconfigure(0, weight=1)
        self.preview_panel.rowconfigure(2, weight=1)

        preview_header = tk.Frame(
            self.preview_panel,
            bg=MAIN_PANEL_HEADER,
            bd=0,
            highlightthickness=0,
            height=MAIN_PREVIEW_HEADER_HEIGHT,
        )
        preview_header.grid(row=0, column=0, sticky="ew")
        preview_header.grid_propagate(False)
        preview_header.columnconfigure(0, weight=1)
        preview_header.rowconfigure(0, weight=1)
        self.preview_title_label = tk.Label(
            preview_header,
            text="Preview",
            bg=MAIN_PANEL_HEADER,
            fg=MAIN_TEXT_PRIMARY,
            font=FONT_PREVIEW_TITLE,
            anchor="w",
        )
        self.preview_title_label.grid(row=0, column=0, sticky="w", padx=(14, 10), pady=0)
        self.preview_select_button = tk.Button(
            preview_header,
            text="Select File",
            command=self.confirm_preview_file,
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=MAIN_SELECT_BUTTON_BACKGROUND,
            activebackground=MAIN_SELECT_BUTTON_ACTIVE,
            fg=MAIN_TEXT_PRIMARY,
            activeforeground=MAIN_TEXT_PRIMARY,
            font=FONT_META_LABEL,
            padx=12,
            pady=5,
            cursor="hand2",
            state="disabled",
            disabledforeground=MAIN_TEXT_SUBTLE,
        )
        self.preview_select_button.grid(
            row=0, column=1, sticky="e", padx=(0, 14), pady=0
        )

        tk.Frame(
            self.preview_panel,
            bg=MAIN_DIVIDER,
            height=1,
            bd=0,
            highlightthickness=0,
        ).grid(row=1, column=0, sticky="ew")

        preview_body = tk.Frame(
            self.preview_panel,
            bg=MAIN_PANEL_BACKGROUND,
            bd=0,
            highlightthickness=0,
        )
        preview_body.grid(row=2, column=0, sticky="nsew")
        preview_body.columnconfigure(0, weight=1)
        preview_body.rowconfigure(0, weight=1)

        self.preview_text_widget = tk.Text(
            preview_body,
            wrap="none",
            font=FONT_CODE,
            padx=10,
            pady=10,
            relief="flat",
            borderwidth=0,
            bg=MAIN_PANEL_BACKGROUND,
            fg=MAIN_TEXT_PRIMARY,
            insertbackground=MAIN_TEXT_PRIMARY,
            selectbackground="#7f7f7f",
            selectforeground=MAIN_TEXT_PRIMARY,
        )
        self.preview_text_widget.grid(row=0, column=0, sticky="nsew")
        self.preview_text_widget.configure(state="disabled")

        self.preview_activate_widgets = [
            self.preview_panel,
            preview_header,
            self.preview_title_label,
            self.preview_text_widget,
        ]
        for widget in self.preview_activate_widgets:
            widget.bind("<Double-Button-1>", self._activate_preview_from_ui, add="+")

        self.main_canvas.bind("<Configure>", self._layout_main_window_shell, add="+")
        self._bind_window_drag(
            self.main_window,
            self.main_canvas,
            self.main_brand_frame,
            brand_row,
            title_label,
            brand_tag,
            self.main_content,
            info_row,
            self.main_active_block,
            self.main_progress_block,
            self.preview_panel,
            preview_header,
            preview_body,
        )

    def _build_settings_window(self) -> None:
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title(f"{APP_TITLE} settings")
        self._configure_borderless_window(
            self.settings_window,
            geometry=DEFAULT_SETTINGS_GEOMETRY,
            minsize=SETTINGS_MIN_SIZE,
            alpha=SETTINGS_ALPHA,
            topmost=True,
            resizable=True,
        )
        self.settings_window.protocol("WM_DELETE_WINDOW", self.hide_settings_window)
        self.settings_canvas, self.settings_surface, container = self._create_window_shell(
            self.settings_window,
            padding=16,
            inner_padding=20,
            palette=(GRADIENT_BLUE, GRADIENT_PURPLE, GRADIENT_GREEN),
        )
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        settings_header = tk.Frame(container, bg=SURFACE_BACKGROUND)
        settings_header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        settings_title = tk.Label(
            settings_header,
            text="settings",
            bg=SURFACE_BACKGROUND,
            fg=TEXT_PRIMARY,
            font=FONT_SETTINGS_TITLE,
            anchor="w",
        )
        settings_title.pack(anchor="w")
        self._bind_window_drag(self.settings_window, settings_header, settings_title)
        self.settings_window.after(
            140,
            lambda: self._apply_window_blur(
                self.settings_window,
                opacity=SETTINGS_ALPHA,
                tint_color=SURFACE_BACKGROUND_ALT,
            ),
        )

        settings_scroll_shell = tk.Frame(container, bg=SURFACE_BACKGROUND, bd=0)
        settings_scroll_shell.grid(row=1, column=0, sticky="nsew", pady=(0, 16))
        settings_scroll_shell.columnconfigure(0, weight=1)
        settings_scroll_shell.rowconfigure(0, weight=1)

        self.settings_scroll_canvas = tk.Canvas(
            settings_scroll_shell,
            highlightthickness=0,
            bd=0,
            relief="flat",
            bg=SURFACE_BACKGROUND,
        )
        self.settings_scroll_canvas.grid(row=0, column=0, sticky="nsew")
        settings_scrollbar = ttk.Scrollbar(
            settings_scroll_shell,
            orient="vertical",
            command=self.settings_scroll_canvas.yview,
            style="Glass.Vertical.TScrollbar",
        )
        settings_scrollbar.grid(row=0, column=1, sticky="ns", padx=(12, 0))
        self.settings_scroll_canvas.configure(yscrollcommand=settings_scrollbar.set)

        self.settings_scroll_content = tk.Frame(
            self.settings_scroll_canvas,
            bg=SURFACE_BACKGROUND,
            bd=0,
        )
        self.settings_scroll_window = self.settings_scroll_canvas.create_window(
            0,
            0,
            anchor="nw",
            window=self.settings_scroll_content,
        )
        self.settings_scroll_content.columnconfigure(0, weight=1)
        self.settings_scroll_content.bind(
            "<Configure>",
            lambda _event: self._layout_scroll_canvas(
                self.settings_scroll_canvas,
                self.settings_scroll_window,
                self.settings_scroll_content,
            ),
        )
        self.settings_scroll_canvas.bind(
            "<Configure>",
            lambda _event: self._layout_scroll_canvas(
                self.settings_scroll_canvas,
                self.settings_scroll_window,
                self.settings_scroll_content,
            ),
        )

        hotkey_card, hotkey_body = self._create_card(
            self.settings_scroll_content,
            title="Hotkeys",
            subtitle="Hotkeys are fixed and cannot be changed.",
        )
        hotkey_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        hotkey_body.columnconfigure(1, weight=1)

        hotkey_display_rows = [
            ("Open main UI", self.config.hotkeys.show_main_ui),
            ("Show/hide all UI (except overlay)", self.config.hotkeys.toggle_visibility),
            ("Open settings", self.config.hotkeys.open_settings),
            ("Select file", self.config.hotkeys.select_file),
            ("Reset active file", self.config.hotkeys.reset_file),
            ("Pause / Resume", self.config.hotkeys.pause_resume),
            ("Show / hide next overlay", self.config.hotkeys.toggle_overlay),
            ("Exit app", self.config.hotkeys.exit_app),
        ]
        for row_index, (label, hotkey_value) in enumerate(hotkey_display_rows):
            tk.Label(
                hotkey_body,
                text=label,
                bg=hotkey_body.cget("bg"),
                fg=TEXT_MUTED,
                font=FONT_BODY,
                anchor="w",
            ).grid(row=row_index, column=0, sticky="w", padx=(0, 12), pady=8)
            tk.Label(
                hotkey_body,
                text=hotkey_value,
                bg=hotkey_body.cget("bg"),
                fg=TEXT_PRIMARY,
                font=FONT_BODY,
                anchor="w",
            ).grid(row=row_index, column=1, sticky="w", pady=8)

        overlay_card, overlay_body = self._create_card(
            self.settings_scroll_content,
            title="Overlay",
        )
        overlay_card.grid(row=2, column=0, sticky="ew")
        overlay_body.columnconfigure(1, weight=1)

        overlay_rows = [
            ("Font size", "font_size"),
            ("Opacity (0.2 - 1.0)", "opacity"),
            ("Horizontal padding", "padding_x"),
            ("Vertical padding", "padding_y"),
            ("Text color", "text_color"),
            ("Total next characters", "next_char_count"),
        ]
        for row_index, (label, key) in enumerate(overlay_rows):
            tk.Label(
                overlay_body,
                text=label,
                bg=overlay_body.cget("bg"),
                fg=TEXT_MUTED,
                font=FONT_BODY,
                anchor="w",
            ).grid(row=row_index, column=0, sticky="w", padx=(0, 12), pady=8)
            entry = tk.Entry(overlay_body, textvariable=self.overlay_vars[key])
            self._style_entry_widget(entry)
            entry.grid(row=row_index, column=1, sticky="ew", pady=8)

        actions = tk.Frame(container, bg=SURFACE_BACKGROUND)
        actions.grid(row=2, column=0, sticky="ew")
        restore_button = self._create_action_button(
            actions, text="Restore Defaults", command=self.restore_default_settings
        )
        restore_button.pack(side="left", padx=(0, 10))
        save_button = self._create_action_button(
            actions, text="Save Settings", command=self.save_settings, accent=True
        )
        save_button.pack(side="left")
        self._bind_canvas_mousewheel(
            self.settings_scroll_canvas,
            self.settings_window,
            self.settings_canvas,
            container,
            settings_scroll_shell,
            self.settings_scroll_canvas,
            self.settings_scroll_content,
            hotkey_card,
            hotkey_body,
            overlay_card,
            overlay_body,
            actions,
        )
        self._bind_window_drag(
            self.settings_window,
            self.settings_canvas,
            self.settings_surface,
            container,
            settings_scroll_shell,
            hotkey_card,
            hotkey_body,
            overlay_card,
            overlay_body,
            actions,
        )

    def _build_overlay_window(self) -> None:
        """Build a pure-text overlay: no background, click-through, left-click draggable."""
        self.overlay_window = tk.Toplevel(self.root)
        self.overlay_window.withdraw()
        self.overlay_window.overrideredirect(True)
        self.overlay_window.geometry("+0+0")
        self.overlay_window.minsize(40, 20)
        # Use a transparent color key for fully transparent background
        TRANSPARENT_COLOR = "#010101"
        self.overlay_window.configure(bg=TRANSPARENT_COLOR, highlightthickness=0, bd=0)
        self.overlay_window.attributes("-alpha", self.config.overlay.opacity)
        self.overlay_window.attributes("-topmost", True)
        self.overlay_window.attributes("-transparentcolor", TRANSPARENT_COLOR)

        self.overlay_transparent_color = TRANSPARENT_COLOR

        # Single label — text only, transparent bg
        self.overlay_label = tk.Label(
            self.overlay_window,
            textvariable=self.overlay_label_var,
            bg=TRANSPARENT_COLOR,
            fg=self.config.overlay.text_color,
            font=(GOOGLE_SANS_FAMILY, self.config.overlay.font_size, "bold"),
            padx=self.config.overlay.padding_x,
            pady=self.config.overlay.padding_y,
            anchor="center",
            justify="center",
        )
        self.overlay_label.pack(fill="both", expand=True)

        # Left-click drag on the text label
        self.overlay_label.bind("<ButtonPress-1>", self._start_overlay_drag)
        self.overlay_label.bind("<B1-Motion>", self._drag_overlay)

        # Make overlay click-through except for the label itself
        self.root.after(140, self._apply_overlay_window_style)

    def _apply_overlay_window_style(self) -> None:
        """Hide from taskbar via WS_EX_TOOLWINDOW. Tkinter handles WS_EX_LAYERED
        internally when -transparentcolor is set, so we must NOT add it ourselves."""
        try:
            hwnd = self.overlay_window.winfo_id()
        except tk.TclError:
            return
        style = GetWindowLongPtr(hwnd, GWL_EXSTYLE)
        style |= WS_EX_TOOLWINDOW
        SetWindowLongPtr(hwnd, GWL_EXSTYLE, style)

    def _start_tray(self) -> None:
        try:
            self.tray_icon = SystemTrayIcon(self.ui_queue)
            self.tray_icon.start()
            self._sync_registered_hotkeys()
        except Exception as exc:
            self.tray_icon = None
            self.native_hotkeys_registered = False
            self.set_status(
                f"System tray gagal start: {exc}. App tetap jalan, tapi tanpa tray."
            )

    def _pump_tray_messages(self) -> None:
        if self.tray_icon:
            self.tray_icon.pump_messages()
        if not self.exiting:
            self.root.after(30, self._pump_tray_messages)

    def _sync_registered_hotkeys(self) -> None:
        if not self.tray_icon:
            self.native_hotkeys_registered = False
            return

        failed_actions = self.tray_icon.register_hotkeys(self.hotkey_actions)
        self.native_hotkeys_registered = len(self.tray_icon.hotkey_ids) > 0
        if failed_actions:
            self.status_text = (
                f"Hotkey gagal diregister: {', '.join(failed_actions)}. Mungkin bentrok dengan app lain."
            )

    def _mark_hotkey_trigger(self, action_name: str) -> bool:
        now = time.monotonic()
        last_triggered = self.hotkey_last_triggered.get(action_name, 0.0)
        if now - last_triggered < HOTKEY_DEBOUNCE_SECONDS:
            return False

        self.hotkey_last_triggered[action_name] = now
        return True

    def _queue_hotkey_action(self, action_name: str) -> bool:
        if not self._mark_hotkey_trigger(action_name):
            return False

        self.ui_queue.put((action_name, "hook_hotkey"))
        return True

    def _install_keyboard_hook(self) -> None:
        self.keyboard_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._keyboard_proc_ref,
            kernel32.GetModuleHandleW(None),
            0,
        )
        if not self.keyboard_hook:
            raise ctypes.WinError(ctypes.get_last_error())

    def _remove_keyboard_hook(self) -> None:
        if self.keyboard_hook:
            user32.UnhookWindowsHookEx(self.keyboard_hook)
            self.keyboard_hook = None

    def _is_character_key(self, virtual_key: int) -> bool:
        """Check if a virtual key is a character-producing key (whitelist approach).
        Only keys that produce a visible character when pressed are whitelisted.
        This excludes operational keys like Esc, Tab, Caps Lock, Shift, Backspace, etc.
        """
        # Modifier keys - never whitelist
        if virtual_key in MODIFIER_KEY_CODES:
            return False
        # Operational keys - not whitelisted
        if virtual_key in OPERATIONAL_VK_CODES:
            return False
        # Letter keys A-Z (0x41-0x5A)
        if 0x41 <= virtual_key <= 0x5A:
            return True
        # Number keys 0-9 (0x30-0x39)
        if 0x30 <= virtual_key <= 0x39:
            return True
        # Numpad numbers 0-9 (0x60-0x69)
        if 0x60 <= virtual_key <= 0x69:
            return True
        # Numpad operators: * + - . / (0x6A-0x6F)
        if 0x6A <= virtual_key <= 0x6F:
            return True
        # Space bar
        if virtual_key == 0x20:
            return True
        # Enter key (VK_RETURN)
        if virtual_key == 0x0D:
            return True
        # OEM keys (symbols like ;=,-./` [\]' etc.) 0xBA-0xDF
        if 0xBA <= virtual_key <= 0xDF:
            return True
        return False

    def _keyboard_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code < 0:
            return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

        keyboard_data = ctypes.cast(
            l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)
        ).contents
        if keyboard_data.flags & LLKHF_INJECTED:
            return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

        virtual_key = keyboard_data.vkCode
        is_key_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
        is_key_up = w_param in (WM_KEYUP, WM_SYSKEYUP)

        if is_key_up and virtual_key in self.suppressed_keyups:
            self.suppressed_keyups.discard(virtual_key)
            return 1

        # Don't intercept when our own windows are in focus
        if self._is_our_process_foreground():
            return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

        if not is_key_down:
            return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

        if not self.active_text:
            return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

        if self.typing_paused:
            return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

        # Check if Ctrl is held — if so, don't intercept (let system combos through)
        ctrl_held = (user32.GetAsyncKeyState(0x11) & 0x8000) != 0
        if ctrl_held:
            return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

        # Handle Backspace: delete char & go back 1 position
        if virtual_key == VK_BACKSPACE:
            if self.current_index > 0:
                self.current_index -= 1
                # Send actual backspace to delete the character in the target
                send_virtual_key(VK_BACKSPACE)
                self.eof_key_consumed = False
                self.status_text = "Karakter dihapus, mundur 1 posisi."
                self._schedule_ui_refresh()
                self.suppressed_keyups.add(virtual_key)
                return 1
            else:
                # Already at the beginning, let backspace pass through
                return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

        # Only intercept whitelisted character keys
        if not self._is_character_key(virtual_key):
            return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

        if virtual_key in MODIFIER_KEY_CODES:
            self.suppressed_keyups.add(virtual_key)
            return 1

        if self.current_index >= len(self.active_text):
            if not self.eof_key_consumed:
                self.eof_key_consumed = True
                self.status_text = (
                    "Akhir file tercapai. Tekan "
                    f"{self.config.hotkeys.reset_file} buat ulang dari awal."
                )
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
                self._schedule_ui_refresh()
                self.suppressed_keyups.add(virtual_key)
                return 1
            return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

        character = self.active_text[self.current_index]
        self._send_character_to_foreground(character)
        self.current_index += 1
        self.eof_key_consumed = False

        if self.current_index >= len(self.active_text):
            self.status_text = "Karakter terakhir sudah dikirim."
        else:
            self.status_text = "Typing global aktif. Next char sudah maju."

        self._schedule_ui_refresh()
        self.suppressed_keyups.add(virtual_key)
        return 1

    def _is_our_process_foreground(self) -> bool:
        foreground = user32.GetForegroundWindow()
        if not foreground:
            return False

        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id))
        return process_id.value == os.getpid()

    def _send_character_to_foreground(self, character: str) -> None:
        if character == "\n":
            send_virtual_key(0x0D)
            return
        if character == "\t":
            send_virtual_key(0x09)
            return
        send_unicode_character(character)

    def _schedule_ui_refresh(self) -> None:
        if self.ui_refresh_pending or self.exiting:
            return
        self.ui_refresh_pending = True
        self.ui_queue.put(("refresh_ui", None))

    def _perform_scheduled_ui_refresh(self) -> None:
        self.ui_refresh_pending = False
        self._refresh_main_labels()
        self._refresh_overlay()

    def _process_ui_queue(self) -> None:
        while True:
            try:
                action_name, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_ui_queue_action(action_name, payload)

        if not self.exiting:
            self.root.after(80, self._process_ui_queue)

    def _handle_ui_queue_action(self, action_name: str, payload: Any) -> None:
        if payload == "native_hotkey" and not self._mark_hotkey_trigger(action_name):
            return

        if action_name == "show_main":
            self.toggle_main_window()
        elif action_name == "show_settings":
            self.toggle_settings_window()
        elif action_name == "select_file":
            self.select_file_via_dialog_from_ui()
        elif action_name == "toggle_visibility":
            self.toggle_visibility()
        elif action_name == "reset_file":
            self.reset_active_file()
        elif action_name == "pause_resume":
            self._toggle_pause_resume()
        elif action_name == "toggle_overlay":
            self._toggle_overlay_visibility()
        elif action_name == "refresh_ui":
            self._perform_scheduled_ui_refresh()
        elif action_name == "exit_app":
            self.shutdown()
        elif action_name == "quit":
            self.shutdown()

    def _refresh_hotkey_map(self) -> None:
        self.hotkey_actions = {}
        hotkey_entries = [
            ("show_main", self.config.hotkeys.show_main_ui),
            ("toggle_visibility", self.config.hotkeys.toggle_visibility),
            ("show_settings", self.config.hotkeys.open_settings),
            ("select_file", self.config.hotkeys.select_file),
            ("reset_file", self.config.hotkeys.reset_file),
            ("pause_resume", self.config.hotkeys.pause_resume),
            ("toggle_overlay", self.config.hotkeys.toggle_overlay),
            ("exit_app", self.config.hotkeys.exit_app),
        ]
        for action_name, hotkey_str in hotkey_entries:
            try:
                modifiers, vk_code = parse_hotkey_string(hotkey_str)
                self.hotkey_actions[action_name] = (modifiers, vk_code)
            except ValueError:
                pass  # Skip invalid hotkey strings
        self._sync_registered_hotkeys()
        self._refresh_button_labels()

    def _refresh_button_labels(self) -> None:
        if not self.main_sidebar_buttons:
            return

        has_active_file = bool(self.active_text)
        self._set_sidebar_button_state("file", active=self.preview_requires_confirmation)
        self._set_sidebar_button_state("reset", muted=not has_active_file)
        self._set_sidebar_button_state(
            "pause", active=self.typing_paused, muted=not has_active_file
        )
        self._set_sidebar_button_state(
            "overlay", active=self.overlay_hidden, muted=not has_active_file
        )
        self._set_sidebar_button_state("settings")
        self._set_sidebar_button_state("exit")

    def _refresh_main_labels(self) -> None:
        preview_label = str(self.preview_path) if self.preview_path else "belum ada"
        self.preview_file_var.set(preview_label)
        self.progress_var.set(f"{self.current_index}/{len(self.active_text)}")
        self.status_var.set(self.status_text)

        if self.preview_requires_confirmation:
            self.preview_state_var.set(f"pending | {self.preview_encoding}")
        elif self.preview_text_value:
            state = "paused" if self.typing_paused else "active"
            self.preview_state_var.set(f"{state} | {self.preview_encoding}")
        else:
            self.preview_state_var.set("belum ada")
        self._refresh_active_file_display()
        self._refresh_button_labels()
        self._sync_preview_interaction_state()

    def _refresh_preview_view(self) -> None:
        self.preview_text_widget.configure(state="normal")
        self.preview_text_widget.delete("1.0", "end")
        if self.preview_text_value:
            self.preview_text_widget.insert("1.0", self.preview_text_value)
        self.preview_text_widget.configure(state="disabled")

    def _should_show_overlay(self) -> bool:
        return (
            bool(self.active_text)
            and not self.overlay_hidden
        )

    def _build_next_chars_string(self) -> str:
        """Build the upcoming characters string based on next_char_count."""
        count = max(1, self.config.overlay.next_char_count)
        end = min(self.current_index + count, len(self.active_text))
        chars = []
        for i in range(self.current_index, end):
            chars.append(describe_character(self.active_text[i]))
        return " ".join(chars) if chars else "-"

    def _refresh_overlay(self) -> None:
        if not self.active_text:
            self.overlay_label_var.set("Next: -")
        elif self.typing_paused:
            chars_str = self._build_next_chars_string() if self.current_index < len(self.active_text) else "-"
            self.overlay_label_var.set(f"Next: {chars_str} (paused)")
        elif self.current_index >= len(self.active_text):
            self.overlay_label_var.set("Next: selesai")
        else:
            chars_str = self._build_next_chars_string()
            self.overlay_label_var.set(f"Next: {chars_str}")

        # Update label style — keep transparent bg
        self.overlay_label.configure(
            bg=self.overlay_transparent_color,
            fg=self.config.overlay.text_color,
            font=(GOOGLE_SANS_FAMILY, self.config.overlay.font_size, "bold"),
            padx=self.config.overlay.padding_x,
            pady=self.config.overlay.padding_y,
        )
        self.overlay_window.attributes("-alpha", self.config.overlay.opacity)

        if self._should_show_overlay():
            self.overlay_window.deiconify()
            self.overlay_window.update_idletasks()
            self._position_overlay()
        else:
            self.overlay_window.withdraw()

    def _position_overlay(self) -> None:
        self.overlay_window.update_idletasks()
        width = self.overlay_window.winfo_reqwidth()
        height = self.overlay_window.winfo_reqheight()
        screen_width = self.overlay_window.winfo_screenwidth()
        screen_height = self.overlay_window.winfo_screenheight()
        if self.config.overlay.x_position < 0 or self.config.overlay.y_position < 0:
            x_position = max(0, (screen_width - width) // 2)
            y_position = max(0, (screen_height - height) // 2)
            self.config.overlay.x_position = x_position
            self.config.overlay.y_position = y_position
        else:
            x_position = max(0, min(self.config.overlay.x_position, screen_width - width))
            y_position = max(0, min(self.config.overlay.y_position, screen_height - height))
            self.config.overlay.x_position = x_position
            self.config.overlay.y_position = y_position
        self.overlay_window.geometry(f"+{x_position}+{y_position}")

    def _window_is_visible(self, window: tk.Toplevel) -> bool:
        try:
            return bool(window.winfo_viewable())
        except tk.TclError:
            return False

    def _set_window_topmost(self, window: tk.Toplevel, enabled: bool = True) -> None:
        try:
            window.attributes("-topmost", enabled)
        except tk.TclError:
            pass

    def _exit_hidden_mode(self) -> None:
        self.hidden_by_shortcut = False
        self.restore_visibility_state = {
            "main": False,
            "settings": False,
        }

    def _sync_window_stack(self) -> None:
        main_visible = self._window_is_visible(self.main_window)
        settings_visible = self._window_is_visible(self.settings_window)

        if main_visible:
            self._set_window_topmost(self.main_window, True)
        if settings_visible:
            self._set_window_topmost(self.settings_window, True)

        if main_visible and settings_visible:
            try:
                self.main_window.lower(self.settings_window)
            except tk.TclError:
                pass
            self.settings_window.lift()
            return

        if settings_visible:
            self.settings_window.lift()
        elif main_visible:
            self.main_window.lift()

    def show_main_window(self, *, focus: bool = True) -> None:
        self._exit_hidden_mode()
        self._present_window(self.main_window, focus=focus)
        self._sync_window_stack()
        self._refresh_overlay()

    def hide_main_window(self) -> None:
        self._hide_main_tooltip()
        self.hide_settings_window()
        self.main_window.withdraw()
        self._refresh_overlay()

    def show_settings_window(self) -> None:
        self._exit_hidden_mode()
        self._sync_settings_vars_from_config()
        self._present_window(self.settings_window)
        self._sync_window_stack()
        self._refresh_overlay()

    def hide_settings_window(self) -> None:
        self.active_hotkey_capture = None
        self.settings_window.withdraw()
        self._sync_window_stack()
        self._refresh_overlay()

    def _present_window(self, window: tk.Toplevel, *, focus: bool = True) -> None:
        window.deiconify()
        self._set_window_topmost(window, True)
        window.lift()
        if focus:
            try:
                window.focus_force()
            except tk.TclError:
                pass

    def toggle_main_window(self) -> None:
        if self._window_is_visible(self.main_window) or self._window_is_visible(
            self.settings_window
        ):
            self.hide_main_window()
            self.set_status("Main UI di-hide.")
        else:
            self.show_main_window()
            self.set_status("Main UI dibuka.")

    def toggle_settings_window(self) -> None:
        if self._window_is_visible(self.settings_window):
            self.hide_settings_window()
            self.set_status("Settings di-hide.")
        else:
            self.show_settings_window()
            self.set_status("Settings dibuka.")

    def toggle_visibility(self) -> None:
        """Toggle visibility of all UI except the next overlay."""
        if not self.hidden_by_shortcut:
            self.restore_visibility_state = {
                "main": self._window_is_visible(self.main_window),
                "settings": self._window_is_visible(self.settings_window),
            }
            self.hidden_by_shortcut = True
            self.main_window.withdraw()
            self.settings_window.withdraw()
            self.set_status("UI di-hide (kecuali overlay). Tekan hotkey lagi buat balikin.")
        else:
            restore_state = dict(self.restore_visibility_state)
            self.hidden_by_shortcut = False
            if restore_state.get("main"):
                self._present_window(self.main_window)
            if restore_state.get("settings"):
                self._sync_settings_vars_from_config()
                self._present_window(self.settings_window)
            self._sync_window_stack()
            self.set_status("UI dibalikin sesuai state terakhir.")
            self._refresh_overlay()

    def select_file_via_dialog_from_ui(self) -> None:
        parent_window = self.settings_window if self._window_is_visible(self.settings_window) else self.main_window
        if not self._window_is_visible(parent_window):
            self.show_main_window()
            parent_window = self.main_window
        selected = filedialog.askopenfilename(
            parent=parent_window,
            title="Pilih file untuk lspdestroyer",
            filetypes=SUPPORTED_FILE_TYPES,
        )
        if not selected:
            self.set_status("Pemilihan file dibatalkan.")
            return

        path = Path(selected)
        if not path.is_file():
            self.set_status("File tidak ditemukan.")
            messagebox.showerror(APP_TITLE, "File yang dipilih tidak ditemukan.")
            return

        text, encoding = load_text_file(path)
        self.preview_path = path
        self.preview_text_value = text
        self.preview_encoding = encoding
        self.preview_requires_confirmation = True
        self._refresh_preview_view()
        self._refresh_main_labels()
        self.set_status("Preview siap.")

    def confirm_preview_file(self) -> None:
        if not self.preview_text_value or not self.preview_path:
            self.set_status("Belum ada preview file yang bisa dipakai.")
            return

        self.active_text = self.preview_text_value
        self.active_path = self.preview_path
        self.active_encoding = self.preview_encoding
        self.preview_requires_confirmation = False
        self.current_index = 0
        self.eof_key_consumed = False
        self.typing_paused = False
        self.overlay_hidden = False
        self.set_status("File aktif.")
        self._refresh_main_labels()
        self._refresh_button_labels()
        self._refresh_overlay()

    def reset_active_file(self) -> None:
        if not self.active_text:
            self.set_status("Belum ada file aktif yang bisa di-reset.")
            return

        self.current_index = 0
        self.eof_key_consumed = False
        self.set_status("Urutan file di-reset ke karakter pertama.")
        self._refresh_main_labels()
        self._refresh_overlay()

    def restore_default_settings(self) -> None:
        defaults = AppConfig()
        self.overlay_vars["font_size"].set(str(defaults.overlay.font_size))
        self.overlay_vars["opacity"].set(str(defaults.overlay.opacity))
        self.overlay_vars["padding_x"].set(str(defaults.overlay.padding_x))
        self.overlay_vars["padding_y"].set(str(defaults.overlay.padding_y))
        self.overlay_vars["text_color"].set(defaults.overlay.text_color)
        self.overlay_vars["next_char_count"].set(str(defaults.overlay.next_char_count))
        self.config.overlay.x_position = -1
        self.config.overlay.y_position = -1

    def _sync_settings_vars_from_config(self) -> None:
        self.overlay_vars["font_size"].set(str(self.config.overlay.font_size))
        self.overlay_vars["opacity"].set(str(self.config.overlay.opacity))
        self.overlay_vars["padding_x"].set(str(self.config.overlay.padding_x))
        self.overlay_vars["padding_y"].set(str(self.config.overlay.padding_y))
        self.overlay_vars["text_color"].set(self.config.overlay.text_color)
        self.overlay_vars["next_char_count"].set(str(self.config.overlay.next_char_count))

    def save_settings(self) -> None:
        try:
            overlay = OverlayConfig(
                font_size=int(self.overlay_vars["font_size"].get()),
                opacity=float(self.overlay_vars["opacity"].get()),
                x_position=self.config.overlay.x_position,
                y_position=self.config.overlay.y_position,
                padding_x=int(self.overlay_vars["padding_x"].get()),
                padding_y=int(self.overlay_vars["padding_y"].get()),
                text_color=self.overlay_vars["text_color"].get().strip(),
                next_char_count=int(self.overlay_vars["next_char_count"].get()),
            )
        except ValueError:
            messagebox.showerror(
                APP_TITLE, "Overlay setting angka harus berisi angka yang valid."
            )
            return

        if overlay.font_size < 6:
            messagebox.showerror(APP_TITLE, "Font size minimal 6.")
            return

        if not 0.2 <= overlay.opacity <= 1.0:
            messagebox.showerror(APP_TITLE, "Opacity harus di antara 0.2 sampai 1.0.")
            return

        if overlay.next_char_count < 1:
            messagebox.showerror(APP_TITLE, "Total next characters minimal 1.")
            return

        try:
            self.root.winfo_rgb(overlay.text_color)
        except tk.TclError:
            messagebox.showerror(
                APP_TITLE,
                "Format warna harus valid, misalnya #f8fafc atau white.",
            )
            return

        self.config = AppConfig(
            hotkeys=self.config.hotkeys,
            overlay=overlay,
        )
        save_config(self.config)
        self._refresh_hotkey_map()
        self._refresh_main_labels()
        self._refresh_overlay()
        self._apply_overlay_window_style()
        self.set_status("Settings disimpan.")
        self.hide_settings_window()

    def set_status(self, message: str) -> None:
        self.status_text = message
        self.status_var.set(message)
        self._refresh_main_labels()
        self._refresh_overlay()

    def shutdown(self) -> None:
        if self.exiting:
            return
        self.exiting = True
        self._hide_main_tooltip()
        self._remove_keyboard_hook()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()
        self.root.destroy()

