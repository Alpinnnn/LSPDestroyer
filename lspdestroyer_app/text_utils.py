from __future__ import annotations

from pathlib import Path


def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def load_text_file(path: Path) -> tuple[str, str]:
    for encoding in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return normalize_line_endings(path.read_text(encoding=encoding)), encoding
        except UnicodeDecodeError:
            continue
    return (
        normalize_line_endings(path.read_text(encoding="utf-8", errors="replace")),
        "utf-8 (replace)",
    )


def describe_character(character: str) -> str:
    if character == "\n":
        return r"\n"
    if character == "\t":
        return r"\t"
    if character == " ":
        return "[space]"
    if character.isprintable():
        return character
    return repr(character)


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    normalized = color.strip().lstrip("#")
    if len(normalized) != 6:
        raise ValueError(f"Unsupported color format: {color}")
    return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))


def mix_color(color_a: str, color_b: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    red_a, green_a, blue_a = hex_to_rgb(color_a)
    red_b, green_b, blue_b = hex_to_rgb(color_b)
    red = int(red_a + (red_b - red_a) * ratio)
    green = int(green_a + (green_b - green_a) * ratio)
    blue = int(blue_a + (blue_b - blue_a) * ratio)
    return f"#{red:02x}{green:02x}{blue:02x}"


def bgra_color(color: str, alpha: int) -> int:
    red, green, blue = hex_to_rgb(color)
    return (alpha << 24) | (blue << 16) | (green << 8) | red
