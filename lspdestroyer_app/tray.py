"""System tray integration and native hotkey registration."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import queue
from typing import Any

from .constants import APP_TITLE, STARTUP_NOTIFICATION
from .hotkeys import MOD_NOREPEAT
from .win32 import (
    IDI_APPLICATION,
    MF_SEPARATOR,
    MF_STRING,
    NIF_ICON,
    NIF_INFO,
    NIF_MESSAGE,
    NIF_TIP,
    NIIF_INFO,
    NIM_ADD,
    NIM_DELETE,
    NIM_MODIFY,
    NOTIFYICONDATAW,
    PM_REMOVE,
    POINT,
    TPM_BOTTOMALIGN,
    TPM_LEFTALIGN,
    TPM_RIGHTBUTTON,
    WM_CLOSE,
    WM_COMMAND,
    WM_CONTEXTMENU,
    WM_DESTROY,
    WM_HOTKEY,
    WM_LBUTTONDBLCLK,
    WM_LBUTTONUP,
    WM_NULL,
    WM_RBUTTONUP,
    WM_TRAYICON,
    WNDCLASSW,
    WndProcType,
    kernel32,
    low_word,
    make_int_resource,
    shell32,
    user32,
    MSG,
)

class SystemTrayIcon:
    MENU_OPEN_MAIN = 1001
    MENU_SELECT_FILE = 1002
    MENU_OPEN_SETTINGS = 1003
    MENU_TOGGLE_VISIBILITY = 1004
    MENU_RESET_FILE = 1005
    MENU_EXIT = 1099

    def __init__(self, ui_queue: queue.Queue[tuple[str, Any]]) -> None:
        self.ui_queue = ui_queue
        self.hwnd: int | None = None
        self.icon_added = False
        self._instance = kernel32.GetModuleHandleW(None)
        self._class_name = f"{APP_TITLE}-tray-{os.getpid()}"
        self._wndproc = WndProcType(self._window_proc)
        self._notify_data = NOTIFYICONDATAW()
        self.hotkey_ids: dict[int, str] = {}

    def start(self) -> None:
        self._register_window_class()
        self._create_window()
        self._add_icon()
        self._show_startup_notification()

    def stop(self) -> None:
        try:
            self.unregister_hotkeys()
            self._delete_icon()
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = None
        finally:
            user32.UnregisterClassW(self._class_name, self._instance)

    def pump_messages(self) -> None:
        if not self.hwnd:
            return

        message = MSG()
        while user32.PeekMessageW(
            ctypes.byref(message), self.hwnd, 0, 0, PM_REMOVE
        ):
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def register_hotkeys(self, hotkey_actions: dict[str, tuple[int, int]]) -> list[str]:
        """Register hotkeys. hotkey_actions maps action_name -> (modifiers, vk_code)."""
        self.unregister_hotkeys()
        if not self.hwnd:
            return list(hotkey_actions.keys())

        failed_actions: list[str] = []
        for offset, (action_name, (modifiers, vk_code)) in enumerate(hotkey_actions.items(), start=1):
            hotkey_id = 3000 + offset
            mod_flags = modifiers | MOD_NOREPEAT
            if user32.RegisterHotKey(self.hwnd, hotkey_id, mod_flags, vk_code):
                self.hotkey_ids[hotkey_id] = action_name
            else:
                failed_actions.append(action_name)
        return failed_actions

    def unregister_hotkeys(self) -> None:
        if not self.hwnd:
            self.hotkey_ids.clear()
            return

        for hotkey_id in list(self.hotkey_ids):
            user32.UnregisterHotKey(self.hwnd, hotkey_id)
        self.hotkey_ids.clear()

    def _register_window_class(self) -> None:
        window_class = WNDCLASSW()
        window_class.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p).value
        window_class.hInstance = self._instance
        window_class.lpszClassName = self._class_name
        atom = user32.RegisterClassW(ctypes.byref(window_class))
        if not atom:
            error_code = ctypes.get_last_error()
            if error_code != 1410:
                raise ctypes.WinError(error_code)

    def _create_window(self) -> None:
        self.hwnd = user32.CreateWindowExW(
            0,
            self._class_name,
            self._class_name,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            self._instance,
            None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

    def _add_icon(self) -> None:
        if not self.hwnd:
            return

        self._notify_data = NOTIFYICONDATAW()
        self._notify_data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self._notify_data.hWnd = self.hwnd
        self._notify_data.uID = 1
        self._notify_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self._notify_data.uCallbackMessage = WM_TRAYICON
        self._notify_data.hIcon = user32.LoadIconW(
            None, make_int_resource(IDI_APPLICATION)
        )
        self._notify_data.szTip = APP_TITLE

        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._notify_data)):
            raise ctypes.WinError(ctypes.get_last_error())

        self.icon_added = True

    def _show_startup_notification(self) -> None:
        if not self.icon_added:
            return

        balloon = NOTIFYICONDATAW()
        ctypes.memmove(
            ctypes.byref(balloon),
            ctypes.byref(self._notify_data),
            ctypes.sizeof(NOTIFYICONDATAW),
        )
        balloon.uFlags = NIF_INFO
        balloon.dwInfoFlags = NIIF_INFO
        balloon.szInfoTitle = APP_TITLE
        balloon.szInfo = STARTUP_NOTIFICATION
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(balloon))

    def _delete_icon(self) -> None:
        if self.icon_added:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._notify_data))
            self.icon_added = False

    def _show_menu(self, hwnd: int) -> None:
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, self.MENU_OPEN_MAIN, "Open Main UI")
        user32.AppendMenuW(menu, MF_STRING, self.MENU_SELECT_FILE, "Select File")
        user32.AppendMenuW(menu, MF_STRING, self.MENU_OPEN_SETTINGS, "Settings")
        user32.AppendMenuW(
            menu, MF_STRING, self.MENU_TOGGLE_VISIBILITY, "Toggle Overlay"
        )
        user32.AppendMenuW(menu, MF_STRING, self.MENU_RESET_FILE, "Reset File")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, self.MENU_EXIT, "Exit")

        cursor_position = POINT()
        user32.GetCursorPos(ctypes.byref(cursor_position))
        user32.SetForegroundWindow(hwnd)
        user32.TrackPopupMenu(
            menu,
            TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_LEFTALIGN,
            cursor_position.x,
            cursor_position.y,
            0,
            hwnd,
            None,
        )
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)

    def _queue_action(self, action_name: str, payload: Any = None) -> None:
        self.ui_queue.put((action_name, payload))

    def _window_proc(
        self, hwnd: int, message: int, w_param: int, l_param: int
    ) -> int:
        if message == WM_TRAYICON:
            if l_param in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self._queue_action("show_main")
                return 0
            if l_param in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu(hwnd)
                return 0

        if message == WM_COMMAND:
            menu_id = low_word(w_param)
            if menu_id == self.MENU_OPEN_MAIN:
                self._queue_action("show_main")
            elif menu_id == self.MENU_SELECT_FILE:
                self._queue_action("select_file")
            elif menu_id == self.MENU_OPEN_SETTINGS:
                self._queue_action("show_settings")
            elif menu_id == self.MENU_TOGGLE_VISIBILITY:
                self._queue_action("toggle_visibility")
            elif menu_id == self.MENU_RESET_FILE:
                self._queue_action("reset_file")
            elif menu_id == self.MENU_EXIT:
                self._queue_action("quit")
            return 0

        if message == WM_HOTKEY:
            action_name = self.hotkey_ids.get(int(w_param))
            if action_name:
                self._queue_action(action_name, "native_hotkey")
                return 0

        if message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0

        if message == WM_DESTROY:
            self._delete_icon()
            return 0

        return user32.DefWindowProcW(hwnd, message, w_param, l_param)

