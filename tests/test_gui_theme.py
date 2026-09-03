"""Self-checks for the GUI palette, styles and the component library."""

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui import components
from gui.theme import FONTS, SPACE, Theme, apply_styles, theme

PALETTE = {
    "bg_app": "#07100A",
    "bg_surface": "#0E1911",
    "bg_surface_raised": "#142219",
    "bg_hover": "#1B3022",
    "border_subtle": "#203527",
    "border_focus": "#42E18B",
    "text_primary": "#EEF7F0",
    "text_secondary": "#A5B9AA",
    "text_disabled": "#65796B",
    "accent": "#35D878",
    "accent_hover": "#58E996",
    "accent_ink": "#04130A",
    "warning": "#F0BD45",
    "danger": "#FF7469",
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

# T-UI-1: body text clears 4.5:1 on every surface it is drawn on, and the status
# colours clear 3:1 as large text and control boundaries.
for surface in ("bg_app", "bg_surface", "bg_surface_raised", "bg_field"):
    assert contrast(theme["text_primary"], theme[surface]) >= 4.5, surface
    assert contrast(theme["text_secondary"], theme[surface]) >= 4.5, surface
    for status in ("accent", "warning", "danger"):
        assert contrast(theme[status], theme[surface]) >= 3.0, (status, surface)

# Text on a tinted pill has to clear its own tint, not the page behind it.
for tint, ink in (("ok_soft", "ok_soft_text"), ("warn_soft", "warn_soft_text"),
                  ("danger_soft", "danger_soft_text")):
    assert contrast(theme[ink], theme[tint]) >= 4.5, tint

# The trap this palette exists to avoid: white on the green accent is unreadable.
assert contrast(theme["accent"], theme["accent_ink"]) >= 4.5
assert contrast(theme["accent"], "#ffffff") < 3.0
source = open(os.path.join(os.path.dirname(__file__), "..", "gui", "theme.py"), encoding="utf-8").read()
assert "#ffffff" not in source.lower(), "gui/theme.py still pairs white with the accent"

# The design's minimum hit height, so a compact control cannot quietly shrink below it.
assert SPACE["hit"] == 44 and SPACE["hit_compact"] == 36
assert SPACE["row"] == 72
assert set(FONTS) >= {"page_title", "section_title", "field_title", "body", "meta", "mono"}

try:
    root = tk.Tk()
except tk.TclError:
    print("skipped: no display")
    sys.exit(0)

root.withdraw()
apply_styles(root)

# T-UI-2: every component builds, and every button kind exists.
outer, inner = components.card(root, "Projects")
outer.pack()
for kind in ("primary", "secondary", "quiet", "danger"):
    widget = components.button(inner, kind.title(), lambda: None, kind=kind,
                               accessible_name=f"{kind} action on CityGuide")
    widget.pack()
    assert int(widget["highlightthickness"]) == 2, "no focus ring on a button"
    enabled_background = widget["background"]

    # A disabled control has to lose its fill, not just its click: a disabled primary
    # left on full accent green still reads as the thing to press.
    components.set_button_state(widget, False)
    assert str(widget["state"]) == "disabled"
    assert widget["background"] == theme["bg_surface_raised"], f"{kind} kept its fill while disabled"
    assert contrast(theme["text_disabled"], widget["background"]) >= 3.0, kind

    components.set_button_state(widget, True)
    assert str(widget["state"]) == "normal"
    assert widget["background"] == enabled_background, f"{kind} did not get its fill back"

for tone in ("ok", "warn", "danger", "neutral"):
    components.pill(inner, f"UE 5.4 {tone}", tone=tone).pack()
components.banner(inner, "Sign in to create or manage Convai projects.", tone="warn",
                  action=("Sign in", lambda: None)).pack()

field = components.Field(inner, "Project name", tk.StringVar(), help_text="Letters, digits and underscores only.")
field.pack(fill="x")
before = field.message["text"]
field.set_error("Project name cannot be empty.")
assert field.message["text"] == "Project name cannot be empty."
field.set_error(None)
assert field.message["text"] == before, "clearing an error must restore the help text"

kind_var = tk.StringVar(value="Scene")
scene = components.ChoiceTile(inner, "Scene", "Environment or gameplay project.", "Scene", kind_var)
avatar = components.ChoiceTile(inner, "Avatar", "Character project.", "Avatar", kind_var)
scene.frame.pack()
avatar.frame.pack()
avatar.select()
root.update_idletasks()
assert kind_var.get() == "Avatar"
assert avatar.frame["highlightbackground"] == theme["accent"], "the selected tile has no accent border"
assert scene.frame["highlightbackground"] == theme["border_subtle"]

steps = components.StepIndicator(inner, ["Details", "Project type", "Unreal Engine"])
steps.frame.pack()
steps.set_current(1)

progress = components.StepList(inner)
progress.frame.pack()
progress.set_steps(["Validated Unreal Engine", "Updating project files"])
progress.set_state("Validated Unreal Engine", "done")
progress.set_state("Updating project files", "active")
progress.set_state("Nothing by that name", "active")  # unknown titles are ignored, not fatal

row = components.ProjectRow(
    inner,
    {"name": "CityGuide", "type": "Scene", "meta": "UE 5.4", "state": "Ready to update",
     "state_colour": "text_secondary", "dir": "E:\\Convai\\CityGuide"},
    on_select=lambda project: None,
)
row.frame.pack(fill="x")
row.set_selected(True)
root.update_idletasks()
assert row.rail["background"] == theme["accent"], "a selected row has no green rail"
row.set_selected(False)
assert row.rail["background"] != theme["accent"]

log = tk.Text(inner)
disclosure = components.Disclosure(inner, "Hide technical log", "Show technical log", log)
disclosure.button.pack()
# winfo_ismapped is False for everything under a withdrawn root, so ask the geometry
# manager whether the widget is packed at all.
assert log.winfo_manager() == "", "the log starts collapsed"
disclosure.toggle()
root.update_idletasks()
assert log.winfo_manager() == "pack", "the disclosure did not reveal its target"
assert disclosure.button["text"] == "Hide technical log"

canvas, host = components.scroll_host(inner)
canvas.container.pack(fill="both", expand=True)

assert components.ellipsise("E:\\Convai\\CityGuide", 64) == "E:\\Convai\\CityGuide"
assert components.ellipsise("x" * 80, 20).startswith("…") and len(components.ellipsise("x" * 80, 20)) == 20

root.update()
root.destroy()
print("ok")
