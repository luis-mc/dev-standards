"""gallery_draw: draws the starter components and token samples as HTML for the design-system gallery (DOCSPEC section 15).

One drawing function per component section, found by the section's title. Values come only from tokens.md (gallery_tokens).
A missing token or one that is not a plain value is drawn with a neutral fallback and a visible 'token missing: <name>' label.
Standard library only. Nothing is loaded from the network.
"""
from __future__ import annotations

import html
import re

import gallery_tokens as T

FB_FG, FB_BG, FB_LINE, FB_SIZE = "#444444", "#eeeeee", "#999999", "1rem"
BG_HINTS = ("page", "surface", "-bg")
TONES = (("done", "Done", "✓"), ("note", "Note", "i"), ("needs-you", "Needs you", "!"), ("problem", "Problem", "✕"))
# text/background pairs the tokens define: (text token, background token, minimum ratio, what it is)
PAIRS = (
    ("color-text", "color-page", 4.5, "body text on page"),
    ("color-text", "color-surface", 4.5, "body text on surface"),
    ("color-text-muted", "color-page", 4.5, "secondary text on page"),
    ("color-text-muted", "color-surface", 4.5, "secondary text on surface"),
    ("color-primary", "color-page", 4.5, "link text on page"),
    ("color-on-primary", "color-primary", 4.5, "text on the primary action"),
    ("color-done", "color-done-bg", 4.5, "Done text on its background"),
    ("color-note", "color-note-bg", 4.5, "Note text on its background"),
    ("color-needs-you", "color-needs-you-bg", 4.5, "Needs you text on its background"),
    ("color-problem", "color-problem-bg", 4.5, "Problem text on its background"),
    ("color-border", "color-surface", 3.0, "control border on surface (UI part)"),
    ("color-focus", "color-page", 3.0, "focus ring on page (UI part)"),
)


def esc(s) -> str:
    return html.escape(str(s), quote=True)


class Draw:
    """Reads tokens for one theme and records the gaps and contrast checks of the sample being drawn."""

    def __init__(self, toks: T.Tokens, theme: str = "light"):
        self.t, self.theme = toks, theme
        self.missing: list = []
        self.checks: list = []  # (label, ratio, need, passed)

    def _gap(self, short: str) -> None:
        if short not in self.missing:
            self.missing.append(short)

    def col(self, short: str) -> str:
        v = self.t.value(short, self.theme)
        if T.is_hex(v):
            return v
        self._gap(short)
        return FB_BG if any(h in short for h in BG_HINTS) else FB_FG

    def size(self, short: str, fb: str = FB_SIZE) -> str:
        v = self.t.value(short, self.theme)
        if T.is_size(v) or (v.endswith("%") and v[:-1].replace(".", "").isdigit()):
            return v
        self._gap(short)
        return fb

    def raw(self, short: str, fb: str) -> str:
        v = self.t.value(short, self.theme)
        if v:
            return v
        self._gap(short)
        return fb

    def shadow(self, short: str) -> str:
        v = self.t.value(short, self.theme)
        if T.is_shadow(v):
            return v
        self._gap(short)
        return "none"

    def edge(self, tone: str) -> str:
        e = self.t.edges.get(tone.replace("-", " "), "")
        if re.fullmatch(r"\d+px (solid|dashed|double|dotted)", e):
            return e
        self._gap(f"tone edge: {tone}")
        return "3px solid"

    def mark(self, fg_short: str, bg_short: str, need: float = 4.5, label: str = "") -> str:
        """A visible ratio and pass/fail word for one text/background pair."""
        a, b = self.t.value(fg_short, self.theme), self.t.value(bg_short, self.theme)
        if not (T.is_hex(a) and T.is_hex(b)):
            self._gap(fg_short if not T.is_hex(a) else bg_short)
            return '<span class="cr na">contrast n/a</span>'
        r = T.contrast(a, b)
        ok = r >= need
        self.checks.append((label or f"{fg_short} on {bg_short}", r, need, ok))
        return f'<span class="cr {"pass" if ok else "fail"}">{T.ratio_text(r)} {"pass" if ok else "FAIL"}</span>'

    # shared pieces
    def fam(self) -> str:
        return esc(self.raw("font-body", "system-ui, sans-serif"))

    def text_style(self, role_size: str, weight: int = 400, color: str = "color-text") -> str:
        return f"font-size:{self.size(role_size)};font-weight:{weight};color:{self.col(color)}"

    def btn(self, label: str, kind: str = "primary", extra: str = "") -> str:
        h, rad, pad = self.size("target-min", "44px"), self.size("radius-2", "8px"), self.size("space-4", "16px")
        base = f"min-height:{h};padding:0 {pad};border-radius:{rad};font:600 {self.size('size-3')} {self.fam()};cursor:pointer;margin:2px 0;"
        if kind == "primary":
            st = f"background:{self.col('color-primary')};color:{self.col('color-on-primary')};border:0"
        elif kind == "secondary":
            st = f"background:{self.col('color-surface')};color:{self.col('color-primary')};border:1px solid {self.col('color-border')}"
        elif kind == "danger":
            st = f"background:{self.col('color-problem-bg')};color:{self.col('color-problem')};border:1px solid {self.col('color-problem')}"
        elif kind == "running":
            st = f"background:{self.col('color-divider')};color:{self.col('color-text-muted')};border:0"
        else:
            st = f"background:transparent;color:{self.col('color-primary')};border:0"
        return f'<button type="button" style="{base}{st};{extra}"{" disabled" if kind == "running" else ""}>{esc(label)}</button>'

    def card(self, inner: str, extra: str = "") -> str:
        return (f'<div style="background:{self.col("color-surface")};border:1px solid {self.col("color-divider")};'
                f'border-radius:{self.size("radius-2", "8px")};padding:{self.size("space-4", "16px")};'
                f'box-shadow:{self.shadow("shadow-1")};{extra}">{inner}</div>')

    def muted(self, s: str) -> str:
        return f'<span style="font-size:{self.size("size-2")};color:{self.col("color-text-muted")}">{s}</span>'

    def title(self, s: str, size: str = "size-5", weight: int = 600) -> str:
        return f'<div style="{self.text_style(size, weight)};line-height:{self.raw("line-height-tight", "1.25")}">{s}</div>'

    def field(self, text: str, w: str = "100%", invalid: bool = False) -> str:
        bc = self.col("color-problem") if invalid else self.col("color-border")
        return (f'<div style="box-sizing:border-box;width:{w};max-width:100%;min-height:{self.size("target-min", "44px")};display:flex;align-items:center;'
                f'padding:0 {self.size("space-3", "12px")};background:{self.col("color-surface")};color:{self.col("color-text")};'
                f'border:1px solid {bc};border-radius:{self.size("radius-1", "4px")}">{esc(text)}</div>')

    def tone_box(self, key: str, word: str, icon: str, text: str) -> str:
        bar = self.size("tone-bar", "12px")
        return (f'<div style="background:{self.col("color-" + key + "-bg")};color:{self.col("color-" + key)};'
                f'border-left:{self.edge(key)} {self.col("color-" + key)};padding:{self.size("space-3", "12px")};'
                f'margin:{self.size("space-2", "8px")} 0;border-radius:{self.size("radius-1", "4px")};min-height:{bar}">'
                f'<strong>{icon} {word}.</strong> {esc(text)} {self.mark("color-" + key, "color-" + key + "-bg")}</div>')

    def picture(self, w: str = "100%", h: str = "88px") -> str:
        return (f'<div role="img" aria-label="picture placeholder" style="width:{w};height:{h};border-radius:{self.size("radius-1", "4px")};'
                f'background:repeating-linear-gradient(45deg,{self.col("color-divider")} 0 8px,{self.col("color-surface")} 8px 16px)"></div>')


def wrap(d: Draw, inner: str) -> str:
    return (f'<div class="canvas" style="background:{d.col("color-page")};color:{d.col("color-text")};font-family:{d.fam()};'
            f'font-size:{d.size("size-3")};line-height:{d.raw("line-height", "1.5")};padding:{d.size("space-4", "16px")}">{inner}</div>')


# ------------------------------------------------------------------ one drawing per component section
def d_page_header(d):
    return (f'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">'
            f'<div>{d.title("Page title", "size-6", 700)}{d.muted("One line that says where you are")}</div>{d.btn("Primary action")}</div>')


def d_top_menu(d):
    cur = f"border-bottom:{d.size('focus-width', '3px')} solid {d.col('color-primary')};font-weight:600"
    items = "".join(f'<span style="padding:8px {d.size("space-3", "12px")};min-height:{d.size("target-min", "44px")};box-sizing:border-box;{cur if i == 0 else ""}">{n}</span>'
                    for i, n in enumerate(("Home", "Projects", "Settings")))
    return (f'<div style="display:flex;flex-wrap:wrap;border-bottom:1px solid {d.col("color-divider")}">{items}</div>'
            f'<p style="margin:8px 0 0">{d.muted("Home › Projects ›")} <strong>Plan</strong></p>')


def d_tabs(d):
    sel = f"border-bottom:{d.size('focus-width', '3px')} solid {d.col('color-primary')};font-weight:600;color:{d.col('color-primary')}"
    items = "".join(f'<span role="tab" style="padding:10px {d.size("space-4", "16px")};{sel if i == 0 else "color:" + d.col("color-text-muted")}">{n}</span>'
                    for i, n in enumerate(("Overview", "Files", "History")))
    return f'<div style="display:flex;flex-wrap:wrap;border-bottom:1px solid {d.col("color-divider")}">{items}</div>' + d.mark("color-primary", "color-page")


def d_wizard(d):
    steps = []
    for i, n in enumerate(("Review", "Moving", "Done")):
        on = i == 0
        steps.append(f'<span style="padding:4px {d.size("space-3", "12px")};border-radius:{d.size("radius-round", "999px")};'
                     f'background:{d.col("color-primary") if on else d.col("color-divider")};color:{d.col("color-on-primary") if on else d.col("color-text")};'
                     f'font-weight:600">{i + 1} {n}</span>')
    return (f'<div style="display:flex;gap:8px;flex-wrap:wrap">{"".join(steps)}</div>'
            f'<p>This will move 12 files. Nothing has changed yet.</p><div style="display:flex;gap:8px;flex-wrap:wrap">{d.btn("Back", "secondary")}{d.btn("Move 12 files")}</div>'
            + d.mark("color-on-primary", "color-primary"))


def d_action_bar(d):
    return d.card(f'{d.muted("12 files will move. You can undo it.")}<div style="display:flex;gap:8px;flex-wrap:wrap">{d.btn("Cancel", "secondary")}{d.btn("Move 12 files")}</div>',
                  f"box-shadow:{d.shadow('shadow-2')}")


def d_action_rows(d):
    row = lambda n, f: (f'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;min-height:{d.size("row", "56px")};'  # noqa: E731
                        f'border-bottom:{d.size("hairline", "1px")} solid {d.col("color-divider")}"><div><strong>{n}</strong><br>{d.muted(f)}</div>{d.btn("Open", "secondary")}</div>')
    return row("Holiday photos", "412 files · 2.1 GB") + row("Receipts", "38 files · 14 MB")


def d_buttons(d):
    ring = f"outline:{d.size('focus-width', '3px')} solid {d.col('color-focus')};outline-offset:{d.size('focus-offset', '2px')}"
    return ('<div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">' + d.btn("Primary") + d.btn("Secondary", "secondary") + d.btn("Quiet", "quiet")
            + d.btn("Delete", "danger") + d.btn("Moving…", "running") + d.btn("Focused", "primary", ring) + "</div>"
            + f'<p>{d.mark("color-on-primary", "color-primary")} primary {d.mark("color-primary", "color-surface")} secondary {d.mark("color-problem", "color-problem-bg")} danger '
            + f'{d.mark("color-focus", "color-page", 3.0)} focus ring (3:1)</p>')


def d_card(d):
    cards = "".join(f'<div style="flex:1 1 {d.size("card-min", "280px")};min-width:0">{d.card(d.title(t) + body)}</div>'
                    for t, body in (("Card", "<p>A boxed section.</p>"), ("Facts", facts(d))))
    return f'<div style="display:flex;gap:{d.size("space-5", "24px")};flex-wrap:wrap">{cards}</div>'


def facts(d):
    return "".join(f'<div style="padding:{d.size("space-2", "8px")} 0;border-top:{d.size("hairline", "1px")} solid {d.col("color-divider")}">{d.muted(n)}<br>{v}</div>'
                   for n, v in (("Size", "2.1 GB"), ("Changed", "2 Nov 2026")))


def d_dialog(d):
    return (f'<div style="background:{d.col("color-surface")};border-radius:{d.size("radius-3", "16px")};box-shadow:{d.shadow("shadow-3")};padding:{d.size("space-5", "24px")};max-width:360px">'
            f'{d.title("Delete 12 files?")}<p>This cannot be undone.</p><div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap">{d.btn("Cancel", "secondary")}{d.btn("Delete", "danger")}</div></div>')


def d_pager(d):
    return f'<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">{d.btn("Previous", "secondary")}<span>Page 2 of 9</span>{d.btn("Next", "secondary")}</div>'


def d_list_toolbar(d):
    line = f"1px solid {d.col('color-border')}"
    chip = lambda s: (f'<span style="padding:6px {d.size("space-3", "12px")};border:{line};border-radius:{d.size("radius-round", "999px")};'  # noqa: E731
                      f'background:{d.col("color-surface")}">{s} ✕</span>')
    top = (f'<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">{d.field("Search", "12rem")}{d.btn("Filter (2)", "secondary")}'
           f'<label style="display:flex;align-items:center;gap:8px">{d.muted("Sort by")}{d.field("Name", "7rem")}</label>{d.muted("42 items")}</div>')
    chips = (f'<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:8px">{chip("Photos")}{chip("2015")}'
             f'<a href="#clear" style="color:{d.col("color-primary")}">Clear all</a></div>')
    sheet = d.card(f'{d.title("Filter", "size-4")}<p>Type: Photos, 2015</p>{d.btn("Show 12 items")}', "margin-top:8px;max-width:20rem")
    return top + chips + d.muted("Filters open in a sheet that ends with the count") + sheet


def d_change_review(d):
    r1, rows = d.size("radius-1", "4px"), []
    count = lambda label, n, on=False: (f'<button type="button" style="min-height:{d.size("target-min", "44px")};padding:0 {d.size("space-3", "12px")};'  # noqa: E731
                                        f'border:1px solid {d.col("color-border")};border-radius:{r1};font:600 {d.size("size-2")} {d.fam()};'
                                        f'background:{d.col("color-primary") if on else d.col("color-surface")};color:{d.col("color-on-primary") if on else d.col("color-text")}">{label} {n}</button>')
    bar = f'<div style="display:flex;gap:8px;flex-wrap:wrap">{count("All", 14, True)}{count("New", 8)}{count("Changed", 4)}{count("Conflict", 2)}</div>'
    kinds = (("done", "+ New", "solid"), ("note", "~ Changed", "solid"), ("needs-you", "! Conflict", "dashed"))
    chips = "".join(f'<span style="padding:4px {d.size("space-2", "8px")};border-radius:{d.size("radius-round", "999px")};background:{d.col("color-" + k + "-bg")};'
                    f'color:{d.col("color-" + k)};font:600 {d.size("size-1")} {d.fam()}">{w} · {n}</span>' for (k, w, _), n in zip(kinds, (8, 4, 2)))
    for key, word, line_style, name, ticked, why in (("done", "+ New", "solid", "Holiday photos", True, ""), ("note", "~ Changed", "solid", "Receipts", True, ""),
                                                    ("needs-you", "! Conflict", "dashed", "Tax 2015", False, "A file with this name is already there. Choose it to replace that file.")):
        rows.append(f'<div style="display:flex;gap:12px;align-items:flex-start;min-height:{d.size("row", "56px")};padding:{d.size("space-2", "8px")} 0;'
                    f'border-bottom:{d.size("hairline", "1px")} {line_style} {d.col("color-" + key)}"><input type="checkbox" {"checked" if ticked else ""} aria-label="{esc(name)}">'
                    f'<div><strong>{name}</strong><br>{d.muted(why) if why else ""}</div>'
                    f'<span style="margin-left:auto;color:{d.col("color-" + key)};font-weight:600">{word}</span></div>')
    sticky = (f'<div style="margin-top:12px;padding:{d.size("space-3", "12px")};background:{d.col("color-surface")};border-top:1px solid {d.col("color-divider")};'
              f'box-shadow:{d.shadow("shadow-2")}">{d.btn("Apply 12 changes")}</div>')
    return (bar + f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0">{chips}</div>' + "".join(rows) + sticky
            + d.mark("color-needs-you", "color-needs-you-bg"))


def d_segmented(d):
    seg = "".join(f'<span style="padding:10px {d.size("space-4", "16px")};min-height:{d.size("target-min", "44px")};box-sizing:border-box;border:1px solid {d.col("color-border")};'
                  f'{"background:" + d.col("color-primary") + ";color:" + d.col("color-on-primary") + ";font-weight:600" if i == 0 else "background:" + d.col("color-surface")}">{n}</span>'
                  for i, n in enumerate(("All", "Open", "Done")))
    chips = "".join(f'<span style="padding:6px {d.size("space-3", "12px")};border:1px solid {d.col("color-border")};border-radius:{d.size("radius-round", "999px")}">{n}</span>' for n in ("Photos", "Docs"))
    return f'<div style="display:flex;flex-wrap:wrap">{seg}</div><div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">{chips}</div>'


def d_one_choice(d):
    return "".join(f'<label style="display:flex;align-items:center;gap:12px;min-height:{d.size("target-min", "44px")}">'
                   f'<input type="radio" name="g{id(d)}" {"checked" if i == 0 else ""}> {n}</label>' for i, n in enumerate(("Move the files", "Copy the files")))


def d_form(d):
    return (f'<label style="{d.text_style("size-3", 600)}">Name</label>{d.field("Holiday photos", d.size("width-field-medium", "20rem"))}'
            f'<div>{d.muted("Letters and numbers. Ends with a full stop.")}</div>'
            f'<label style="{d.text_style("size-3", 600)}">Folder</label>{d.field("", d.size("width-field-short", "8rem"), True)}'
            f'<div style="color:{d.col("color-problem")}">✕ Problem. Enter a folder. {d.mark("color-problem", "color-page")}</div>')


def d_tables(d):
    td = f"padding:8px;border-bottom:{d.size('hairline', '1px')} solid {d.col('color-divider')};text-align:left"
    rows = "".join(f'<tr><td style="{td}">{a}</td><td style="{td};text-align:right">{b}</td></tr>' for a, b in (("Holiday photos", "412"), ("Receipts", "38")))
    return f'<table style="border-collapse:collapse;width:100%"><tr><th style="{td}">Name</th><th style="{td};text-align:right">Files</th></tr>{rows}</table>'


def d_progress(d):
    r = d.size("radius-round", "999px")
    unknown = f"repeating-linear-gradient(45deg,{d.col('color-primary')} 0 8px,{d.col('color-divider')} 8px 16px)"
    return (f'<div style="height:8px;background:{d.col("color-divider")};border-radius:{r}"><div style="width:50%;height:8px;background:{d.col("color-primary")};border-radius:{r}"></div></div>'
            f'<p>Page 12 of 24</p><div style="height:8px;background:{unknown};border-radius:{r}"></div><p>{d.muted("Total not known: static striped fill")}</p>')


def d_badges(d):
    out = []
    for key, word, icon in TONES:
        out.append(f'<span style="display:inline-block;padding:2px {d.size("space-2", "8px")};margin:0 8px 8px 0;border-radius:{d.size("radius-1", "4px")};'
                   f'background:{d.col("color-" + key + "-bg")};color:{d.col("color-" + key)};font:600 {d.size("size-1")} {d.fam()}">{icon} {word} {d.mark("color-" + key, "color-" + key + "-bg")}</span>')
    return "".join(out) + f'<span style="background:{d.col("color-primary")};color:{d.col("color-on-primary")};border-radius:{d.size("radius-round", "999px")};padding:2px 8px;font-weight:600">12</span>'


def d_messages(d):
    banner = (f'<div style="background:{d.col("color-needs-you-bg")};color:{d.col("color-needs-you")};padding:{d.size("space-3", "12px")};box-shadow:{d.shadow("shadow-2")}">'
              f'<strong>! Needs you.</strong> The app-wide banner. {d.mark("color-needs-you", "color-needs-you-bg")}</div>')
    return "".join(d.tone_box(k, w, i, "A short message that says what happened.") for k, w, i in TONES) + banner


def d_states(d):
    one = lambda t, s, b: d.card(f'{d.title(t)}<p>{s}</p>{b}', "margin-bottom:8px")  # noqa: E731
    return one("Nothing here yet", "Add a folder to begin.", d.btn("Add a folder")) + one("Could not load", "The list did not load.", d.btn("Try again", "secondary")) + d.tone_box("problem", "Problem", "✕", "Something went wrong.")


def d_selection_bar(d):
    return (f'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;background:{d.col("color-primary")};color:{d.col("color-on-primary")};'
            f'padding:{d.size("space-3", "12px")};border-radius:{d.size("radius-2", "8px")}"><strong>3 selected</strong><span>Move · Delete · Clear</span> {d.mark("color-on-primary", "color-primary")}</div>')


def d_search(d):
    return f'<div style="display:flex;gap:8px;flex-wrap:wrap">{d.field("Search files", "16rem")}{d.btn("Search")}</div><p>{d.muted("18 results for “holiday”")}</p>'


def d_check_row(d):
    return (f'<div style="display:flex;align-items:center;gap:12px;min-height:{d.size("target-min", "44px")}"><input type="checkbox" checked style="width:{d.size("target-min", "44px")};height:20px">'
            f'<div><div>Holiday photos</div>{d.muted("412 files")}</div><span style="margin-left:auto">2.1 GB</span></div>')


def d_slider(d):
    return (f'<label>Quality: 70</label><div style="position:relative;height:{d.size("target-min", "44px")}"><div style="position:absolute;top:20px;left:0;right:0;height:4px;background:{d.col("color-divider")}"></div>'
            f'<div style="position:absolute;top:20px;left:0;width:70%;height:4px;background:{d.col("color-primary")}"></div>'
            f'<div style="position:absolute;top:10px;left:70%;width:24px;height:24px;margin-left:-12px;border-radius:50%;background:{d.col("color-primary")};border:{d.size("focus-offset", "2px")} solid {d.col("color-surface")}"></div></div>')


def d_time_axis(d):
    return "".join(f'<div style="display:flex;gap:12px;padding:8px 0;border-left:{d.size("focus-offset", "2px")} solid {d.col("color-border")};padding-left:12px"><strong>{a}</strong><span>{b}</span></div>'
                   for a, b in (("14:05", "Scan finished"), ("13:40", "Scan started"), ("Yesterday", "Folder added")))


def d_jump_map(d):
    cells = "".join(f'<span style="display:inline-block;width:{d.size("space-5", "24px")};height:{d.size("space-5", "24px")};margin:2px;text-align:center;'
                    f'background:{d.col("color-primary") if i == 3 else d.col("color-divider")};color:{d.col("color-on-primary") if i == 3 else d.col("color-text")}">{i + 1}</span>' for i in range(10))
    return f'<div>{cells}</div>' + d.muted("Page 4 of 10")


def d_live_log(d):
    return (f'<div role="log" style="font:{d.size("size-2")} {esc(d.raw("font-mono", "monospace"))};background:{d.col("color-surface")};border:1px solid {d.col("color-divider")};'
            f'padding:{d.size("space-3", "12px")};border-radius:{d.size("radius-1", "4px")}">14:05:01 Scan started<br>14:05:09 412 files found<br>14:05:12 Done</div>')


def d_activity(d):
    return (f'<div style="display:flex;align-items:center;gap:8px;padding:{d.size("space-2", "8px")};background:{d.col("color-note-bg")};color:{d.col("color-note")}">'
            f'<span style="width:8px;height:8px;border-radius:50%;background:{d.col("color-note")}"></span>Scanning 12 of 40 {d.mark("color-note", "color-note-bg")}</div>')


def d_dates(d):
    return ('<div style="font-variant-numeric:tabular-nums">2 Nov 2026, 14:05<br>1,234 files<br><span style="display:inline-block;min-width:6rem;text-align:right">2.1 GB</span></div>'
            + d.muted("Equal years collapse: 2015, not 2015-2015"))


def d_export(d):
    return f'<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">{d.btn("Export table", "secondary")}{d.muted("12 rows · CSV")}</div>'


def d_picture_card(d):
    cards = "".join(f'<div style="flex:1 1 8rem;min-width:0">{d.card(d.picture() + "<div>Photo " + str(i) + "</div>")}</div>' for i in (1, 2))
    rail = "".join(f'<div style="flex:0 0 6rem">{d.picture("6rem", "4rem")}</div>' for _ in range(4))
    return f'<div style="display:flex;gap:12px;flex-wrap:wrap">{cards}</div><div style="display:flex;gap:8px;overflow-x:auto;margin-top:8px">{rail}</div>'


def d_chart(d):
    bars = "".join(f'<rect x="{10 + i * 40}" y="{80 - h}" width="28" height="{h}" fill="{d.col("color-primary")}"></rect>'
                   f'<text x="{24 + i * 40}" y="96" text-anchor="middle" font-size="10" fill="{d.col("color-text")}">{n}</text>' for i, (n, h) in enumerate((("Mon", 30), ("Tue", 55), ("Wed", 40), ("Thu", 70))))
    return (f'<svg viewBox="0 0 180 100" width="180" role="img" aria-label="Files per day: Mon 30, Tue 55, Wed 40, Thu 70" style="max-width:100%">{bars}</svg>'
            f'<table style="border-collapse:collapse"><tr><td>Mon 30 · Tue 55 · Wed 40 · Thu 70</td></tr></table>' + d.mark("color-primary", "color-page", 3.0, "chart bars (UI part)"))


def d_shared_rules(d):
    note = lambda s: f'<div style="margin:2px 0 10px">{d.muted("↑ " + s)}</div>'  # noqa: E731
    return (f'<div style="display:flex;gap:8px;flex-wrap:wrap">{d.btn("Move all 12 files")}{d.btn("Preview", "secondary")}{d.btn("Delete", "danger")}</div>'
            + note("One primary per region; secondary beside it; danger asks first")
            + f'<a href="#shared-rules" style="color:{d.col("color-primary")}">A link</a> · <span style="padding:0 6px;border:1px solid {d.col("color-divider")};border-radius:{d.size("radius-1", "4px")}">Tag</span> · {d.muted("2015 · 412 files")}'
            + note("Link for navigation; a tag is flat; metadata uses a middle dot")
            + f'<div style="border-bottom:{d.size("hairline", "1px")} solid {d.col("color-divider")};font-weight:600">Section heading</div>'
            + note("Hairline, no heavy box"))


def d_other_parts(d):
    return (f'<div>✓ Done · ! Needs you · ✕ Problem {d.muted("(an icon always has a word)")}</div>'
            + f'<div style="margin:8px 0">{d.field("Folder", "12rem")}{d.muted("Pick the folder to scan.")}</div>'
            + f'<div style="display:flex;align-items:center;gap:12px;min-height:{d.size("target-min", "44px")};border-top:{d.size("hairline", "1px")} solid {d.col("color-divider")}">'
              f'<input type="checkbox"> <div>Holiday photos<br>{d.muted("412 files")}</div><span style="margin-left:auto">›</span></div>')


DRAWINGS = {
    "page header": d_page_header, "top menu and breadcrumbs": d_top_menu, "tabs": d_tabs, "wizard": d_wizard,
    "sticky action bar": d_action_bar, "action rows": d_action_rows, "buttons": d_buttons,
    "card, card grid and facts list": d_card, "dialog and sheet": d_dialog, "pager": d_pager, "list toolbar": d_list_toolbar, "change review": d_change_review,
    "segmented choices and filter chips": d_segmented, "one-choice list": d_one_choice, "form field family": d_form,
    "tables and list rows": d_tables, "progress bar": d_progress, "badges and counts": d_badges, "messages and banner": d_messages,
    "empty, failed and error states": d_states, "selection bar": d_selection_bar, "search bar and find layout": d_search,
    "check box row": d_check_row, "slider": d_slider, "time axis list": d_time_axis, "page jump map": d_jump_map,
    "live log": d_live_log, "activity strip": d_activity, "dates, times and numbers": d_dates, "table export": d_export,
    "picture card, grid and rail": d_picture_card, "chart with a text alternative": d_chart,
    "shared component rules": d_shared_rules, "other shared parts": d_other_parts,
}
# Sections that state rules and have no part of their own. They are drawn as an annotated sample of what the rule governs.
RULE_SECTIONS = {"shared component rules"}

SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$", re.M)


def parse_components(text: str) -> list:
    """[(number, title, body)] for each numbered '## N. Title' section of components.md."""
    ms = list(SECTION_RE.finditer(text or ""))
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        body = text[m.end():end]
        body = re.split(r"^##\s", body, 1, flags=re.M)[0]
        out.append((int(m.group(1)), m.group(2), body))
    return out


def used_for(body: str) -> str:
    m = re.search(r"\*\*Used for:\*\*\s*(.+)", body)
    s = m.group(1).strip() if m else ""
    first = re.split(r"(?<=\.)\s", s, 1)[0]
    return first[:240]


def themes_for(toks: T.Tokens) -> list:
    return ["light", "dark"] if toks.has_dark() else ["light"]


def panels(toks: T.Tokens, fn, gaps: dict, failures: list, what: str) -> str:
    """Draw `fn` once per theme, side by side. Adds visible 'token missing' labels and records gaps and failed contrast checks."""
    cells = []
    drawn = []
    for th in themes_for(toks):
        d = Draw(toks, th)
        inner = fn(d)
        drawn.append((th, d, inner))
    missing = []
    for _, d, _ in drawn:
        for m in d.missing:
            if m not in missing:
                missing.append(m)
    for m in missing:
        gaps.setdefault(m, []).append(what)
    for th, d, inner in drawn:
        for label, r, need, ok in d.checks:
            if not ok:
                failures.append(f"{what} ({th}): {label} is {T.ratio_text(r)}, needs {need:g}:1")
        cells.append(f'<div class="theme"><p class="meta">{th}</p>{wrap(d, inner)}</div>')
    labels = "".join(f'<p class="gap">token missing: {esc(m if m.startswith(("tone edge", "role ")) else toks.name(m))}</p>' for m in missing)
    return f'<div class="pair">{"".join(cells)}</div>{labels}'


# ------------------------------------------------------------------ token kinds that are not colour swatches or plain sizes
def _pair_fn(toks):
    def fn(d):
        out = []
        for text, fill in toks.fill_pairs():
            out.append(f'<span style="display:inline-block;margin:0 8px 8px 0;padding:6px {d.size("space-3", "12px")};border-radius:{d.size("radius-1", "4px")};'
                       f'border:1px solid {d.col("color-divider")};background:{d.col(fill)};color:{d.col(text)};font-weight:600">'
                       f'Aa {esc(text[len("color-"):])} on {esc(fill[len("color-"):])} {d.mark(text, fill, 4.5, text + " on " + fill)}</span>')
        return "".join(out) or '<p class="meta">No on-fill pairs found.</p>'
    return fn


def token_kind_samples(toks: T.Tokens, gaps: dict, failures: list) -> list:
    """Drawn sections for text-on-fill pairs, motion, per-width tokens, border widths and weights. Returns [(id, label, html)]."""
    pre = toks.prefix
    sec = []
    sec.append(("fills", "Text on a fill", "<h2>Text on a fill</h2><p class='meta'>Each sample is text on its own fill, with its contrast ratio. The -bg tokens equal the tint.</p>"
                + panels(toks, _pair_fn(toks), gaps, failures, "text on a fill")))

    def table(head, rows):
        return ("<table><thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in head) + "</tr></thead><tbody>"
                + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>")

    motion = [(f"<code>{esc(pre + n)}</code>", esc(v), esc(u)) for n, v, u in toks.with_prefix("duration-")]
    widths = [(f"<code>{esc(n)}</code>", *[f"{esc(c)}: {esc(v)}" for c, v in cols]) for n, cols in toks.widths.items()]
    wcols = max((len(w) for w in widths), default=1)
    widths = [w + ("",) * (wcols - len(w)) for w in widths]
    frames = [(f"<code>{esc(pre + n)}</code>", esc(v), esc(u)) for n, v, u in toks.with_prefix("frame-") + toks.with_prefix("control-height")]
    weights = [(f"<code>{esc(pre + n)}</code>", esc(v), f'<span style="font-weight:{esc(v)}">Sample text</span>') for n, v, _ in toks.with_prefix("weight-")]

    def border_fn(d):
        return '<div class="demo">' + "".join(
            f'<div style="background:{d.col("color-surface")};color:{d.col("color-text")};width:96px;height:48px;'
            f'border:{d.size(n, "1px")} {"double" if n.endswith("double") else "solid"} {d.col("color-border")}">{esc(n[len("border-"):])} {esc(v)}</div>'
            for n, v, _ in toks.with_prefix("border-")) + "</div>"

    def role_fn(d):
        out = []
        for role, r in toks.roles.items():
            wt = r["weight"] if r["weight"].isdigit() else "400"
            ceil = r.get("ceiling", "")
            bad = ceil.isdigit() and wt.isdigit() and int(wt) > int(ceil)
            out.append(f'<div style="font-weight:{wt};color:{d.col("color-text")}">{esc(role)} · weight {esc(wt)}, ceiling {esc(ceil or "none")}'
                       f'{" ✕ above its ceiling" if bad else ""}</div>')
            if bad:
                d.checks.append((f"role {role} weight {wt} above ceiling {ceil}", 0.0, 1.0, False))
        return "".join(out)

    sec.append(("motion", "Motion", "<h2>Motion</h2>" + (table(("Token", "Value", "Use"), motion) if motion else "<p class='meta'>No duration tokens found.</p>")))
    sec.append(("per-width", "Per width", "<h2>Per width and sizes</h2>" + (table(("Token",) + tuple(f"Width {i + 1}" for i in range(wcols)), widths) if widths else "<p class='meta'>No per-width tokens found.</p>")
                + (table(("Token", "Value", "Use"), frames) if frames else "")))
    sec.append(("borders", "Border widths", "<h2>Border widths</h2>" + panels(toks, border_fn, gaps, failures, "border widths")))
    sec.append(("weights", "Weights", "<h2>Weight per type role</h2>" + (table(("Token", "Value", "Sample"), weights) if weights else "") + panels(toks, role_fn, gaps, failures, "weights")))
    return sec
