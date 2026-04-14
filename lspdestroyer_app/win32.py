from __future__ import annotations

import ctypes
from ctypes import wintypes

from .constants import WINDOW_BACKGROUND
from .text_utils import bgra_color


def make_int_resource(value: int) -> wintypes.LPCWSTR:
    return ctypes.cast(ctypes.c_void_p(value), wintypes.LPCWSTR)


def low_word(value: int) -> int:
    return value & 0xFFFF


WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
LLKHF_INJECTED = 0x00000010

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001

WM_TRAYICON = 0x0400 + 100
WM_COMMAND = 0x0111
WM_CONTEXTMENU = 0x007B
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_NULL = 0x0000
WM_HOTKEY = 0x0312
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020
TPM_LEFTALIGN = 0x0000
PM_REMOVE = 0x0001

IDI_APPLICATION = 32512
WCA_ACCENT_POLICY = 19
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

ULONG_PTR = wintypes.WPARAM
HINSTANCE = wintypes.HANDLE
HICON = wintypes.HANDLE
HCURSOR = wintypes.HANDLE
HBRUSH = wintypes.HANDLE
HHOOK = wintypes.HANDLE
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
LRESULT = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", INPUTUNION)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", WPARAM),
        ("lParam", LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", HINSTANCE),
        ("hIcon", HICON),
        ("hCursor", HCURSOR),
        ("hbrBackground", HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", HICON),
    ]


class ACCENTPOLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", wintypes.DWORD),
        ("AccentFlags", wintypes.DWORD),
        ("GradientColor", wintypes.DWORD),
        ("AnimationId", wintypes.DWORD),
    ]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attrib", ctypes.c_int),
        ("pvData", ctypes.c_void_p),
        ("cbData", ctypes.c_size_t),
    ]


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    LRESULT, ctypes.c_int, WPARAM, LPARAM
)
WndProcType = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM
)

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = HINSTANCE
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = ctypes.c_ushort
user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, HINSTANCE]
user32.UnregisterClassW.restype = wintypes.BOOL
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HANDLE,
    HINSTANCE,
    ctypes.c_void_p,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    LowLevelKeyboardProc,
    HINSTANCE,
    wintypes.DWORD,
]
user32.SetWindowsHookExW.restype = HHOOK
user32.CallNextHookEx.argtypes = [HHOOK, ctypes.c_int, WPARAM, LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [
    wintypes.HWND,
    ctypes.c_int,
    wintypes.UINT,
    wintypes.UINT,
]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT
shell32.Shell_NotifyIconW.argtypes = [
    wintypes.DWORD,
    ctypes.POINTER(NOTIFYICONDATAW),
]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

SetWindowCompositionAttribute = getattr(user32, "SetWindowCompositionAttribute", None)
if SetWindowCompositionAttribute:
    SetWindowCompositionAttribute.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA),
    ]
    SetWindowCompositionAttribute.restype = wintypes.BOOL

if hasattr(user32, "GetWindowLongPtrW"):
    GetWindowLongPtr = user32.GetWindowLongPtrW
    SetWindowLongPtr = user32.SetWindowLongPtrW
else:
    GetWindowLongPtr = user32.GetWindowLongW
    SetWindowLongPtr = user32.SetWindowLongW


def keyboard_input(
    *, virtual_key: int = 0, scan_code: int = 0, flags: int = 0
) -> INPUT:
    packet = INPUT()
    packet.type = INPUT_KEYBOARD
    packet.ki = KEYBDINPUT(virtual_key, scan_code, flags, 0, 0)
    return packet


def send_virtual_key(virtual_key: int) -> None:
    packets = (INPUT * 2)(
        keyboard_input(virtual_key=virtual_key),
        keyboard_input(virtual_key=virtual_key, flags=KEYEVENTF_KEYUP),
    )
    user32.SendInput(len(packets), packets, ctypes.sizeof(INPUT))


def send_unicode_character(character: str) -> None:
    units = character.encode("utf-16-le")
    packets: list[INPUT] = []
    for index in range(0, len(units), 2):
        code_unit = int.from_bytes(units[index : index + 2], "little")
        packets.append(keyboard_input(scan_code=code_unit, flags=KEYEVENTF_UNICODE))
        packets.append(
            keyboard_input(
                scan_code=code_unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
            )
        )
    packet_array = (INPUT * len(packets))(*packets)
    user32.SendInput(len(packets), packet_array, ctypes.sizeof(INPUT))


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except OSError:
        try:
            user32.SetProcessDPIAware()
        except OSError:
            pass


def enable_window_blur(hwnd: int, *, tint_color: str = WINDOW_BACKGROUND) -> None:
    if not SetWindowCompositionAttribute:
        return

    accent = ACCENTPOLICY()
    accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND
    accent.AccentFlags = 2
    accent.GradientColor = bgra_color(tint_color, 210)
    accent.AnimationId = 0

    data = WINDOWCOMPOSITIONATTRIBDATA()
    data.Attrib = WCA_ACCENT_POLICY
    data.pvData = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
    data.cbData = ctypes.sizeof(accent)

    try:
        SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
    except OSError:
        pass
