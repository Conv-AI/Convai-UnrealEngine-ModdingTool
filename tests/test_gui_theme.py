"""Self-checks for the GUI palette, styles and widget factory."""

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.theme import Theme, WidgetFactory, apply_styles, theme, widgets

PALETTE = {
    "bg_dark": "#0A0F0C",
    "bg_card": "#111814",
    "bg_input": "#18211C",
    "bg_toolbar": "#050806",
    "border": "#243029",
    "text": "#E4EDE7",
    "text_muted": "#8FA396",
    "accent": "#2FD07A",
    "accent_hover": "#4FE494",
    "on_accent": "#04140B",
    "warning": "#E8B339",
    "error": "#FF6B5E",
}


def contrast(hex_a: str, hex_b: str) -> float:
    """WCAG 2.x contrast ratio between two #rrggbb colours."""
    def luminance(value: str) -> float:
        rgb = [int(value.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light, dark = sorted((luminance(hex_a), luminance(hex_b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


assert theme is Theme(), "Theme is not a singleton"
for key, value in PALETTE.items():
    assert theme[key].lower() == value.lower(), f"{key} is {theme[key]}, expected {value}"
assert theme["success"].lower() == PALETTE["accent"].lower()

assert contrast(theme["accent"], theme["on_accent"]) >= 4.5
# The trap this palette exists to avoid: white on the green accent is unreadable.
assert contrast(theme["accent"], "#ffffff") < 3.0

source = open(os.path.join(os.path.dirname(__file__), "..", "gui", "theme.py"), encoding="utf-8").read()
assert "#ffffff" not in source.lower(), "gui/theme.py still pairs white with the accent"

try:
    root = tk.Tk()
except tk.TclError:
    print("skipped: no display")
    sys.exit(0)

root.withdraw()
apply_styles(root)

factory = widgets
assert isinstance(factory, WidgetFactory)

_, inner = factory.create_card(root, "Your projects")
factory.create_button(inner, "Update", lambda: None, style="accent")
factory.create_button(inner, "Delete", lambda: None, style="danger", width=10)
factory.create_button(inner, "Cancel", lambda: None)
factory.create_text_field(inner, "Project name", tk.StringVar(), hint="letters, digits, underscore")
factory.create_text_field(inner, "API key", tk.StringVar(), show="•")
factory.create_segmented(inner, "Asset type", [("Scene", "scene"), ("Avatar", "avatar")], tk.StringVar(value="scene"))
factory.create_dropdown(inner, "Engine", tk.StringVar(), ["5.6", "5.8"], hint="detected from the registry")

root.update()
root.destroy()
print("ok")
