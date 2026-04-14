from __future__ import annotations


SPECIAL_VK_CODES = {
    "PageUp": 0x21,
    "PageDown": 0x22,
    "End": 0x23,
    "Home": 0x24,
    "Insert": 0x2D,
    "Delete": 0x2E,
    "Pause": 0x13,
    "Space": 0x20,
    "Enter": 0x0D,
    "Backspace": 0x08,
}
VK_NAME_TO_CODE = {
    **SPECIAL_VK_CODES,
    **{f"F{number}": 0x6F + number for number in range(1, 13)},
    **{chr(code): code for code in range(ord("A"), ord("Z") + 1)},
    **{str(number): ord(str(number)) for number in range(10)},
}
VK_CODE_TO_NAME = {code: name for name, code in VK_NAME_TO_CODE.items()}
KEY_TOKEN_ALIASES = {
    "pageup": "PageUp",
    "pgup": "PageUp",
    "pagedown": "PageDown",
    "pgdn": "PageDown",
    "ins": "Insert",
    "insert": "Insert",
    "del": "Delete",
    "delete": "Delete",
    "home": "Home",
    "end": "End",
    "pause": "Pause",
    "space": "Space",
    "spacebar": "Space",
    "enter": "Enter",
    "return": "Enter",
    "backspace": "Backspace",
    "bksp": "Backspace",
}
MODIFIER_KEY_CODES = {
    0x10,  # VK_SHIFT
    0x11,  # VK_CONTROL
    0x12,  # VK_MENU (Alt)
    0x14,  # VK_CAPITAL (Caps Lock)
    0x5B,  # VK_LWIN
    0x5C,  # VK_RWIN
    0xA0,  # VK_LSHIFT
    0xA1,  # VK_RSHIFT
    0xA2,  # VK_LCONTROL
    0xA3,  # VK_RCONTROL
    0xA4,  # VK_LMENU
    0xA5,  # VK_RMENU
}
# Operational keys that should NOT trigger typing (non-character keys)
OPERATIONAL_VK_CODES = {
    0x08,  # VK_BACK (Backspace) - handled separately
    0x09,  # VK_TAB
    0x13,  # VK_PAUSE
    0x14,  # VK_CAPITAL (Caps Lock)
    0x1B,  # VK_ESCAPE
    0x21,  # VK_PRIOR (Page Up)
    0x22,  # VK_NEXT (Page Down)
    0x23,  # VK_END
    0x24,  # VK_HOME
    0x25,  # VK_LEFT
    0x26,  # VK_UP
    0x27,  # VK_RIGHT
    0x28,  # VK_DOWN
    0x2C,  # VK_SNAPSHOT (Print Screen)
    0x2D,  # VK_INSERT
    0x2E,  # VK_DELETE
    0x5B,  # VK_LWIN
    0x5C,  # VK_RWIN
    0x5D,  # VK_APPS
    0x90,  # VK_NUMLOCK
    0x91,  # VK_SCROLL
    *range(0x70, 0x88),  # F1-F24
}
VK_BACKSPACE = 0x08
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000


def normalize_key_token(token: str, *, allow_extended: bool = False) -> str | None:
    cleaned = token.strip()
    if not cleaned:
        return None

    canonical = KEY_TOKEN_ALIASES.get(cleaned.lower())
    if canonical:
        if allow_extended or canonical in VK_NAME_TO_CODE:
            return canonical
        return None

    if len(cleaned) == 1:
        candidate = cleaned.upper()
        if candidate in VK_NAME_TO_CODE:
            return candidate

    return None


def parse_blacklist_keys(raw_value: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for chunk in raw_value.replace("\n", ",").replace(";", ",").split(","):
        normalized = normalize_key_token(chunk, allow_extended=True)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keys.append(normalized)
    return keys


def parse_hotkey_string(hotkey_str: str) -> tuple[int, int]:
    """Parse a hotkey string like 'Ctrl+O' into (modifiers, vk_code)."""
    parts = [part.strip() for part in hotkey_str.split("+")]
    modifiers = 0
    key_name = parts[-1]
    for mod in parts[:-1]:
        if mod.lower() == "ctrl":
            modifiers |= MOD_CONTROL
    vk = VK_NAME_TO_CODE.get(key_name)
    if vk is None:
        raise ValueError(f"Unknown key: {key_name}")
    return modifiers, vk
