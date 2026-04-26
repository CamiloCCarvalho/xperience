"""
Paleta fixa do Mural (chaves persistidas, hex resolvidos no backend/frontend).
"""

from __future__ import annotations

from typing import Final

MURAL_COLOR_HEX: Final[dict[str, str]] = {
    "red": "#db1f28",
    "orange": "#e15319",
    "aqua": "#197e86",
    "blue": "#2772cd",
    "green": "#20b153",
    "yellow": "#c5b607",
    "pink": "#d709a4",
    "purple": "#a416f3",
}

MURAL_COLOR_CHOICES: Final[tuple[tuple[str, str], ...]] = tuple(
    (k, k) for k in MURAL_COLOR_HEX.keys()
)


def mural_color_keys() -> frozenset[str]:
    return frozenset(MURAL_COLOR_HEX.keys())


def mural_color_hex(key: str | None) -> str | None:
    if not key:
        return None
    return MURAL_COLOR_HEX.get(key)


def validate_mural_color_key(value: str | None, *, field_name: str = "color_key") -> None:
    from django.core.exceptions import ValidationError

    if value in (None, ""):
        return
    if value not in MURAL_COLOR_HEX:
        raise ValidationError({field_name: "Cor inválida. Use apenas uma opção da paleta do mural."})


def mural_palette_for_ui() -> list[dict[str, str]]:
    return [{"key": k, "hex": v} for k, v in MURAL_COLOR_HEX.items()]
