"""Build the presentation deck from the pipeline outputs.

Usage:
    .venv/bin/python deck/build_deck.py        # -> deck/saatva_affiliate_analysis.pptx

Ten slides plus three backup slides. Each slide carries one message, one chart or
visual, and few words; the detail is in the speaker notes. The numbers come from
outputs/*.csv; the case studies and external benchmarks are written into the text.

Charts are drawn with plain shapes rather than embedded chart objects: Google Slides
turns imported charts into pictures, while shapes stay editable there. Fonts are
Georgia (titles) and Arial (everything else), which Google Slides and Keynote both have.

Palette: Partnerize's orange and blues frame the deck; Saatva's bronze marks the client.
Chart marks use a richer step of that bronze (S_MARK), which passes the colour-blind
checks against the other hues; the brand bronze itself is kept for large fills.
"""
import csv
import math
import os

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "deck", "saatva_affiliate_analysis.pptx")

# Palette ---------------------------------------------------------------------------
NAVY = "0B2A4A"            # dark base and titles
P_DEEP = "006BA1"          # Partnerize deep blue
P_BLUE = "368EF8"          # Partnerize blue
P_ORANGE = "FF9438"        # Partnerize orange: hijack signals
ORANGE_TEXT = "C9620E"     # the orange, darkened for text on white
ORANGE_TINT = "FFF1E5"
S_BRONZE = "C19678"        # Saatva bronze, for large fills
S_MARK = "B5793F"          # Saatva bronze, chart step (validated against the other hues)
BRONZE_TINT = "F6EFE8"
BLUE_TINT = "EAF2FE"
INK = "1E2833"
MUTED = "647282"
GRID = "E3E8EE"
PANEL = "F3F6F9"
GREY_MARK = "B7C1CC"       # competitors
GREY_LIGHT = "D5DCE4"      # the retail benchmark
WHITE = "FFFFFF"

TITLE_FONT = "Georgia"
BODY_FONT = "Arial"

W, H = 13.333, 7.5
L, R = 0.6, 12.733         # content edges
CW = R - L

FOOTER = "Saatva affiliate analysis  ·  Hagay Gross"
REPO = "github.com/Hagaygro/partnerize-assignment"
NO_TABLE_STYLE = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"   # "No Style, No Grid"

ALIGN = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}
ANCHOR = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}


# Data ------------------------------------------------------------------------------
def load():
    def rows(name):
        with open(os.path.join(ROOT, "outputs", name + ".csv")) as f:
            return list(csv.DictReader(f))

    mix = {}
    for r in rows("traffic_mix"):
        mix.setdefault(r["brand"], {})[r["entry_source"]] = int(r["visits"])
    return {
        "comp": {r["brand"]: r for r in rows("competitor_summary")},
        "mix": mix,
        "sens": {(r["brand"], r["look_back"]): r for r in rows("hijack_sensitivity")},
        "signal": {r["primary_signal"][2:]: r for r in rows("signal_summary") if r["brand"] == "Walmart"},
        "valid": {r["brand"]: r for r in rows("scaling_validation")},
        "scaling": rows("scaling")[0],
        "dq": rows("dq_profile")[0],
        "incr": {(r["stage"], r["grp"].startswith("Affiliate")): r for r in rows("incrementality")},
        "incr_sum": rows("incrementality_summary")[0],
        "risk": {r["scope"]: r for r in rows("commission_at_risk")},
    }


def num(v):
    return float(v) if v not in ("", None) else 0.0


def r0(v):
    """Round half up: 10.5 -> 11."""
    return int(math.floor(num(v) + 0.5))


def k(v):
    """16706 -> 16.7K, 625 -> 0.6K, 121977 -> 122K, 7023454 -> 7.0M; below 500 as is."""
    v = num(v)
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    if v >= 1e5:
        return f"{v / 1e3:.0f}K"
    if v >= 500:
        return f"{v / 1e3:.1f}K"
    return f"{v:.0f}"


def pct(v, digits=1):
    return f"{num(v):.{digits}f}%"


# Drawing helpers -------------------------------------------------------------------
def rgb(h):
    return RGBColor.from_string(h)


def _plain(shape):
    """Drop the theme style python-pptx gives new shapes (some apps draw it as a shadow)."""
    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)


def _runs(p, s, size, color, font, bold, italic, accent, spc, accent_bold=True):
    """Add `s` to paragraph `p`; **marked** parts are bold (and coloured `accent`, if given)."""
    for i, part in enumerate(s.split("**")):
        if not part:
            continue
        r = p.add_run()
        r.text = part
        f = r.font
        f.name, f.size, f.italic = font, Pt(size), italic
        marked = i % 2 == 1
        f.bold = bold or (marked and accent_bold)
        f.color.rgb = rgb(accent if marked and accent else color)
        if spc:
            f._rPr.set("spc", str(spc))


def fill_text(tf, paras, size=14, color=INK, font=BODY_FONT, bold=False, italic=False, align="l",
              spacing=1.1, after=0, accent=None, spc=None, accent_bold=True):
    """Write paragraphs into a text frame. A paragraph is a string or (string, options)."""
    if not isinstance(paras, list):
        paras = paras.split("\n")
    for i, para in enumerate(paras):
        o = {}
        if isinstance(para, tuple):
            para, o = para
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = ALIGN[o.get("align", align)]
        p.line_spacing = o.get("spacing", spacing)
        p.space_after = Pt(o.get("after", after))
        _runs(p, para, o.get("size", size), o.get("color", color), o.get("font", font),
              o.get("bold", bold), o.get("italic", italic), o.get("accent", accent), o.get("spc", spc),
              o.get("accent_bold", accent_bold))


def text(slide, x, y, w, h, paras, anchor="t", **kw):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = ANCHOR[anchor]
    fill_text(tf, paras, **kw)
    return tb


def box(slide, x, y, w, h, fill=None, line=None, line_w=0.75, shape=MSO_SHAPE.RECTANGLE, radius=None):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    _plain(s)
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(line_w)
    else:
        s.line.fill.background()
    if radius is not None:
        s.adjustments[0] = radius
    return s


def label_box(slide, x, y, w, h, paras, fill, anchor="m", margin=0.12, shape=MSO_SHAPE.RECTANGLE,
              radius=None, line=None, line_w=0.75, **kw):
    """A filled shape with text inside."""
    s = box(slide, x, y, w, h, fill=fill, shape=shape, radius=radius, line=line, line_w=line_w)
    tf = s.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = Inches(margin)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = ANCHOR[anchor]
    fill_text(tf, paras, **kw)
    return s


def pill(slide, x, y, w, label, fill, color, h=0.34, size=12, line=None):
    return label_box(slide, x, y, w, h, label, fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5,
                     margin=0.08, size=size, color=color, bold=True, align="c", line=line)


def dot(slide, x, y, color, d=0.16):
    return box(slide, x, y, d, d, fill=color, shape=MSO_SHAPE.OVAL)


def number_badge(slide, x, y, n, color, d=0.42, size=14):
    return label_box(slide, x, y, d, d, str(n), color, shape=MSO_SHAPE.OVAL, margin=0, size=size,
                     color=WHITE, bold=True, align="c")


def line(slide, x1, y1, x2, y2, color=GRID, w=0.75, arrow=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    _plain(c)
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(w)
    if arrow:
        end = etree.SubElement(c.line._get_or_add_ln(), qn("a:tailEnd"))
        end.set("type", "triangle")
        end.set("w", "med")
        end.set("len", "med")
    return c


def hbar(slide, x, y, w, h, color):
    """A horizontal bar from the baseline at x, rounded at the data end only."""
    if w < h:                                         # too short to round
        return box(slide, x, y, max(w, 0.02), h, fill=color)
    cx, cy = x + w / 2, y + h / 2
    s = slide.shapes.add_shape(MSO_SHAPE.ROUND_2_SAME_RECTANGLE,
                               Inches(cx - h / 2), Inches(cy - w / 2), Inches(h), Inches(w))
    _plain(s)
    s.rotation = 90                                   # the rounded top edge becomes the right end
    s.adjustments[0] = 0.14
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(color)
    s.line.fill.background()
    return s


def legend(slide, x, y, items, size=12):
    """Swatch + muted label per series, left to right."""
    for label, color in items:
        box(slide, x, y + 0.04, 0.16, 0.16, fill=color)
        text(slide, x + 0.25, y, 5, 0.26, label, size=size, color=MUTED)
        x += 0.25 + 0.088 * len(label) + 0.4


def lens(slide, ax, ay, bx, by, r, fill, steps=48):
    """The overlap of two equal circles, as a freeform."""
    d = math.hypot(bx - ax, by - ay)
    t = math.atan2(by - ay, bx - ax)
    a = math.acos(d / (2 * r))
    pts = [(ax + r * math.cos(t - a + 2 * a * i / steps), ay + r * math.sin(t - a + 2 * a * i / steps))
           for i in range(steps + 1)]
    pts += [(bx + r * math.cos(t + math.pi - a + 2 * a * i / steps),
             by + r * math.sin(t + math.pi - a + 2 * a * i / steps)) for i in range(steps + 1)]
    emu = [(int(Inches(px)), int(Inches(py))) for px, py in pts]
    fb = slide.shapes.build_freeform(emu[0][0], emu[0][1], scale=1.0)
    fb.add_line_segments(emu[1:], close=True)
    s = fb.convert_to_shape()
    _plain(s)
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    s.line.fill.background()
    return s


def _cell_borders(cell, bottom=None, w=0.75):
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        old = tcPr.find(qn(tag))
        if old is not None:
            tcPr.remove(old)
    for i, (tag, color) in enumerate((("a:lnL", None), ("a:lnR", None), ("a:lnT", None), ("a:lnB", bottom))):
        ln = etree.Element(qn(tag))
        ln.set("w", str(Pt(w)) if color else "0")
        if color:
            etree.SubElement(etree.SubElement(ln, qn("a:solidFill")), qn("a:srgbClr")).set("val", color)
        else:
            etree.SubElement(ln, qn("a:noFill"))
        tcPr.insert(i, ln)


def table(slide, x, y, widths, rows, heights, size=12, header_size=11, fills=None, aligns=None, bold_cols=(0,)):
    """rows[0] is the header. fills: per-row background (None = white)."""
    gf = slide.shapes.add_table(len(rows), len(widths), Inches(x), Inches(y),
                                Inches(sum(widths)), Inches(sum(heights)))
    tbl = gf.table
    tblPr = tbl._tbl.tblPr
    tblPr.set("firstRow", "0")
    tblPr.set("bandRow", "0")
    sid = tblPr.find(qn("a:tableStyleId"))
    if sid is None:
        sid = etree.SubElement(tblPr, qn("a:tableStyleId"))
    sid.text = NO_TABLE_STYLE
    for j, w in enumerate(widths):
        tbl.columns[j].width = Inches(w)
    for i, h in enumerate(heights):
        tbl.rows[i].height = Inches(h)
    for i, row in enumerate(rows):
        head = i == 0
        for j, val in enumerate(row):
            c = tbl.cell(i, j)
            c.margin_left = c.margin_right = Inches(0.08)
            c.margin_top = c.margin_bottom = Inches(0.03)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            c.fill.fore_color.rgb = rgb(NAVY if head else (fills[i] if fills and fills[i] else WHITE))
            fill_text(c.text_frame, val, size=header_size if head else size, color=WHITE if head else INK,
                      bold=head or j in bold_cols, align=aligns[j] if aligns else "l", spacing=1.0)
            _cell_borders(c, bottom=None if head else GRID)
    return tbl


# Slide frame -----------------------------------------------------------------------
def content_slide(prs, n, kicker, title, notes):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    text(s, L, 0.42, 10, 0.3, kicker.upper(), size=11, color=ORANGE_TEXT, bold=True, spc=150)
    text(s, L, 0.72, CW, 0.75, title, size=32, color=NAVY, font=TITLE_FONT, spacing=1.0)
    text(s, L, 7.02, 9, 0.25, FOOTER, size=9, color=MUTED)
    dot(s, R - 0.5, 7.065, P_ORANGE, 0.14)
    dot(s, R - 0.41, 7.065, P_BLUE, 0.14)
    text(s, R - 0.22, 7.02, 0.22, 0.25, str(n), size=9, color=MUTED, align="r")
    s.notes_slide.notes_text_frame.text = notes
    return s


# Slides ----------------------------------------------------------------------------
def slide_title(prs, d):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    box(s, 0, 0, W, H, fill=NAVY)
    # Partnership motif: two Partnerize circles, Saatva bronze where they overlap.
    ax, ay, bx, by, r = 10.95, 2.7, 12.65, 4.2, 1.85
    box(s, ax - r, ay - r, 2 * r, 2 * r, fill=P_ORANGE, shape=MSO_SHAPE.OVAL)
    box(s, bx - r, by - r, 2 * r, 2 * r, fill=P_BLUE, shape=MSO_SHAPE.OVAL)
    lens(s, ax, ay, bx, by, r, S_BRONZE)
    text(s, 0.8, 1.45, 8.4, 0.3, "PARTNERIZE  ·  SENIOR DATA ANALYST HOME ASSIGNMENT",
         size=12, color=P_ORANGE, bold=True, spc=200)
    text(s, 0.8, 1.95, 7.9, 1.75, "**Saatva's** affiliate program vs. US mattress competitors",
         size=42, color=WHITE, font=TITLE_FONT, accent="D9BC9F", accent_bold=False, spacing=1.0)
    text(s, 0.8, 3.85, 8.0, 0.4, "Clicks and conversions  ·  Growth levers  ·  Attribution hijacking",
         size=17, color="C9D6E3")
    text(s, 0.8, 5.72, 8, 0.32, "Hagay Gross", size=16, color=WHITE, bold=True)
    dq = d["dq"]
    text(s, 0.8, 6.08, 9, 0.3,
         f"October 2026  ·  Data: US clickstream panel, 1 May 2026 "
         f"({num(dq['rows']) / 1e6:.1f}M events, {num(dq['users']) / 1e3:.0f}K users)",
         size=11.5, color="9FB3C8")
    s.notes_slide.notes_text_frame.text = (
        "Three questions for Saatva: how its US affiliate program compares with Nectar, Helix, DreamCloud and "
        "Walmart; how to grow it; and how to control attribution hijacking. The data is a one-day US "
        "clickstream panel: 48.4M events from 784K users on 1 May 2026.")


def stat_tile(s, x, y, w, h, kicker, mark, value, label, context, value_size=54):
    box(s, x, y, w, h, fill=PANEL)
    dot(s, x + 0.3, y + 0.33, mark)
    text(s, x + 0.55, y + 0.27, w - 0.8, 0.28, kicker, size=12, color=MUTED, bold=True)
    text(s, x + 0.3, y + 0.62, w - 0.6, 0.95, value, size=value_size, color=NAVY, bold=True)
    text(s, x + 0.3, y + 1.6, w - 0.6, 0.55, label, size=15, color=INK, bold=True, spacing=1.05)
    text(s, x + 0.3, y + 2.2, w - 0.6, 0.35, context, size=12.5, color=MUTED)


def slide_answer(prs, d):
    s = content_slide(prs, 2, "The answer", "Affiliate is Saatva's edge; quality is the next lever", (
        "Three numbers. First, 16% of Saatva's visits start with an affiliate click, against 4–11% for the other "
        "mattress brands, and Similarweb independently ranks affiliate as Saatva's #1 channel. Second, scaled to "
        "the US, that is about 16.7K affiliate clicks a day. The range is wide, 6.1K–36.4K, because it rests on six "
        "panel clicks; at category conversion rates it means roughly 84–334 orders a day. Third, where the data "
        "has volume (Walmart), the 13–24% of clicks that carry a hijack signal take 52–79% of the "
        "affiliate-credited orders, and Saatva's own clicks already show the same patterns. So the "
        "recommendations split in two: grow the channel, and stop paying for credit that was taken, not earned."))
    c = d["comp"]
    sa = c["Saatva"]
    rivals = [num(c[b]["pct_visits_from_affiliate"]) for b in ("Nectar", "Helix", "DreamCloud")]
    s30, s2 = d["sens"][("Walmart", "30 min (base)")], d["sens"][("Walmart", "2 min")]
    tiles = [
        ("Saatva · traffic share", S_MARK, f"{r0(sa['pct_visits_from_affiliate'])}%",
         "of visits start with an affiliate click", f"Rivals: {r0(min(rivals))}–{r0(max(rivals))}%"),
        ("Saatva · US volume", S_MARK, "~" + k(sa["est_us_affiliate_clicks"]), "affiliate clicks a day",
         f"Range {k(sa['est_us_affiliate_clicks_lo95'])}–{k(sa['est_us_affiliate_clicks_hi95'])}  ·  "
         f"{k(sa['est_us_converted_clicks_benchmark_lo'])}–{k(sa['est_us_converted_clicks_benchmark_hi'])} orders a day"),
        ("Walmart · hijacking", P_ORANGE, f"{r0(s2['pct_orders_from_strong'])}–{r0(s30['pct_orders_from_strong'])}%",
         "of affiliate orders go to flagged clicks",
         f"Only {r0(s2['pct_clicks_strong'])}–{r0(s30['pct_clicks_strong'])}% of clicks carry the signals"),
    ]
    tw, gap = (CW - 2 * 0.3) / 3, 0.3
    for i, t in enumerate(tiles):
        stat_tile(s, L + i * (tw + gap), 1.65, tw, 2.75, *t)
    cols = [("Grow the program", S_MARK, BRONZE_TINT,
             ["Recruit review and HSA/FSA partners", "Give each publisher its own coupon code",
              "Pay for the assist, not the last touch"]),
            ("Protect it from hijacking", P_ORANGE, ORANGE_TINT,
             ["Reconcile clicks with site landings", "No commission overwrite after a cart",
              "Extension stand-down and a PPC policy"])]
    pw = (CW - 0.3) / 2
    for i, (head, color, tint, items) in enumerate(cols):
        x = L + i * (pw + 0.3)
        box(s, x, 4.65, pw, 2.1, fill=tint)
        text(s, x + 0.3, 4.82, pw - 0.6, 0.35, head, size=17, color=NAVY, bold=True)
        for j, item in enumerate(items):
            y = 5.33 + j * 0.45
            number_badge(s, x + 0.3, y, j + 1, color, d=0.3, size=11)
            text(s, x + 0.78, y + 0.01, pw - 1.0, 0.3, item, size=15, color=INK)


def slide_share(prs, d):
    s = content_slide(prs, 3, "Results · traffic mix", "Affiliate drives 16% of Saatva's visits, the top share", (
        "The share of visits that start with an affiliate click is the most robust comparison, because it doesn't "
        "depend on scaling: Saatva 16%, Helix 10.5%, DreamCloud 7.4%, Nectar 3.9%. Nectar and DreamCloud lean "
        "on paid search instead, 43% and 37% of their visits. Similarweb agrees independently: affiliate is the "
        "#1 channel for Saatva (23.7% of traffic) and Helix (21.0%), paid search for Nectar and DreamCloud. "
        "Caveat: one day gives 19–51 visits per mattress brand, so read the order, not the decimals."))
    c, mix = d["comp"], d["mix"]
    rows = [("Saatva", S_MARK, ("Affiliate · 23.7%", BLUE_TINT, P_DEEP)),
            ("Helix", GREY_MARK, ("Affiliate · 21.0%", BLUE_TINT, P_DEEP)),
            ("DreamCloud", GREY_MARK, ("Paid search", PANEL, MUTED)),
            ("Nectar", GREY_MARK, ("Paid search", PANEL, MUTED)),
            ("Walmart", GREY_LIGHT, None)]
    x0, scale, y0, pitch, bh = 2.6, 0.34, 2.3, 0.78, 0.32
    text(s, x0, 1.72, 6.5, 0.26, "Share of visits that start with an affiliate click", size=12, color=MUTED,
         bold=True)
    text(s, 9.95, 1.72, 2.8, 0.26, "Similarweb: #1 channel", size=12, color=MUTED, bold=True)
    for i, (b, color, sw) in enumerate(rows):
        y = y0 + i * pitch + (0.25 if b == "Walmart" else 0)
        share = num(c[b]["pct_visits_from_affiliate"])
        visits = sum(mix[b].values())
        client = b == "Saatva"
        text(s, L, y - 0.05, 1.9, 0.3, b, size=16, color=INK, bold=client)
        text(s, L, y + 0.25, 1.9, 0.25, "retail benchmark" if b == "Walmart" else f"{visits} visits",
             size=11, color=MUTED)
        hbar(s, x0, y, share * scale, bh, color)
        text(s, x0 + share * scale + 0.12, y + 0.01, 1.0, 0.3, f"{share:.1f}%", size=15, color=INK,
             bold=client)
        if sw:
            label, fill_c, text_c = sw
            pill(s, 9.95, y - 0.01, 2.6, label, fill_c, text_c, line=None if fill_c == BLUE_TINT else GREY_LIGHT)
    line(s, x0, y0 - 0.2, x0, y0 + 4 * pitch + 0.62, INK, 0.75)
    nectar = mix["Nectar"]
    dream = mix["DreamCloud"]
    text(s, L, 6.4, CW, 0.3,
         f"US panel visits, 1 May 2026. Nectar and DreamCloud lean on paid search: "
         f"{100 * nectar['Paid search'] / sum(nectar.values()):.0f}% and "
         f"{100 * dream['Paid search'] / sum(dream.values()):.0f}% of their visits.",
         size=12, color=MUTED)


def slide_volume(prs, d):
    s = content_slide(prs, 4, "Results · US estimates", "Saatva: ~16.7K US affiliate clicks a day", (
        "US estimate = panel clicks × a scale factor calibrated on the mattress audience (next slide). Saatva comes "
        "to about 16.7K clicks a day, with a 95% interval of 6.1K–36.4K; with the Walmart-calibrated factor the "
        "conservative estimate is 6.5K. The four intervals overlap, so one day can't rank the mattress brands by "
        "volume. No mattress order followed an affiliate click within the day, which is expected for a "
        "considered purchase, so orders use a 0.5–2% category conversion rate: 84–334 a day for Saatva. Walmart has "
        "the volume to measure directly: 6,449 panel clicks, 1.72% converting, so about 7.0M clicks and 121K "
        "converting clicks a day."))
    c = d["comp"]
    order = ["Saatva", "Nectar", "Helix", "DreamCloud"]
    x0, x1, vmax = 2.6, 8.9, 40000
    sc = (x1 - x0) / vmax
    y0, pitch = 2.45, 0.86
    top, bottom = 1.95, y0 + 3 * pitch + 0.42
    text(s, x0, 1.62, 6.3, 0.26, "Affiliate clicks a day: estimate and 95% interval", size=12, color=MUTED,
         bold=True)
    for t in range(0, vmax + 1, 10000):
        gx = x0 + t * sc
        line(s, gx, top, gx, bottom, INK if t == 0 else GRID, 0.75)
        text(s, gx - 0.4, bottom + 0.08, 0.8, 0.25, f"{t // 1000}K" if t else "0", size=11, color=MUTED,
             align="c")
    text(s, 9.55, 1.62, 3.2, 0.26, "Orders a day (est.)", size=12, color=MUTED, bold=True)
    for i, b in enumerate(order):
        r = c[b]
        y = y0 + i * pitch
        client = b == "Saatva"
        color = S_MARK if client else GREY_MARK
        lo, hi, est = (num(r["est_us_affiliate_clicks_lo95"]), num(r["est_us_affiliate_clicks_hi95"]),
                       num(r["est_us_affiliate_clicks"]))
        text(s, L, y - 0.17, 1.9, 0.32, b, size=16, color=INK, bold=client)
        box(s, x0 + lo * sc, y - 0.05, (hi - lo) * sc, 0.1, fill=color)
        box(s, x0 + est * sc - 0.12, y - 0.12, 0.24, 0.24, fill=color, shape=MSO_SHAPE.OVAL, line=WHITE,
            line_w=2)
        text(s, x0 + est * sc - 0.5, y - 0.47, 1.0, 0.26, k(est), size=13, color=INK, bold=True, align="c")
        text(s, 9.55, y - 0.17, 3.2, 0.32,
             f"{k(r['est_us_converted_clicks_benchmark_lo'])}–{k(r['est_us_converted_clicks_benchmark_hi'])}",
             size=16, color=INK, bold=client)
    text(s, 9.55, bottom + 0.08, 3.2, 0.5, "At a 0.5–2% category conversion rate", size=11, color=MUTED)
    wm = c["Walmart"]
    text(s, L, 6.3, CW, 0.5,
         f"The intervals overlap: one day can't rank the mattress brands by volume.  Walmart, for scale: "
         f"~{k(wm['est_us_affiliate_clicks'])} clicks a day, {pct(wm['pct_clicks_converting'], 2)} convert "
         f"(~{k(wm['est_us_converted_clicks'])}).",
         size=12, color=MUTED)


def slide_method(prs, d):
    s = content_slide(prs, 5, "Method", "Cleaned data, scaled on the right audience", (
        "Validation changed the answer. 14.7% of rows were exact duplicates, and some people were recorded under "
        "two user ids, one a partial copy of the other; left as is, that inflated brand visits by 14–28% and "
        "orders by 20%. I merged ids that share three or more identical events. One pass selects the users who "
        "touched any of the five brands, so everything runs on 3.4% of the data, in about 30 seconds. "
        "Scaling: a factor calibrated on walmart.com recovers only 35–50% of the mattress sites' Similarweb "
        "traffic, because the panel under-covers that audience. The mattress brands therefore use a factor "
        "calibrated on the mattress sites themselves, which reproduces each brand within 0.89–1.27×. Caveat: "
        "Similarweb's latest public month is August, the Labor Day sale season."))
    dq, sc, v = d["dq"], d["scaling"], d["valid"]
    clicks = sum(num(r["panel_affiliate_clicks"]) for r in d["comp"].values())
    steps = [(f"{num(dq['rows']) / 1e6:.1f}M", f"panel events from {num(dq['users']) / 1e3:.0f}K users, one day"),
             ("1.64M", "events of users who touched a brand (3.4%)"),
             (k(clicks), "US affiliate clicks, de-duplicated by click id"),
             ("× F", "scaled to US totals, per audience")]
    bw, gap = 2.75, (CW - 4 * 2.75) / 3
    for i, (big, desc) in enumerate(steps):
        x = L + i * (bw + gap)
        box(s, x, 1.7, bw, 1.05, fill=PANEL)
        text(s, x + 0.25, 1.8, bw - 0.4, 0.45, big, size=26, color=NAVY, bold=True)
        text(s, x + 0.25, 2.28, bw - 0.4, 0.45, desc, size=12, color=INK, spacing=1.0)
        if i < 3:
            line(s, x + bw + 0.06, 2.22, x + bw + gap - 0.06, 2.22, P_ORANGE, 1.5, arrow=True)
    dup = 100 * num(dq["duplicate_rows"]) / num(dq["rows"])
    pill(s, L + bw + gap, 2.88, bw, f"−{dup:.1f}% duplicate rows", ORANGE_TINT, ORANGE_TEXT, size=11.5)
    pill(s, L + bw + gap, 3.3, bw, "Mirror user IDs merged", ORANGE_TINT, ORANGE_TEXT, size=11.5)

    text(s, L, 3.9, 8, 0.26, "Scaled panel visits ÷ Similarweb visits  (1.0 = exact match)", size=12,
         color=MUTED, bold=True)
    legend(s, L, 4.22, [(f"Walmart-calibrated factor ({num(sc['scale_factor_retail']):,.0f})", GREY_MARK),
                        (f"Mattress-calibrated factor ({num(sc['scale_factor_mattress']):,.0f})", P_BLUE)])
    x0, scale, y0, pitch, bh = 2.6, 5.0, 4.95, 0.6, 0.22
    for i, b in enumerate(("Saatva", "Nectar", "DreamCloud")):
        y = y0 + i * pitch
        text(s, L, y + 0.07, 1.9, 0.3, b, size=15, color=INK, bold=b == "Saatva")
        for j, (col, color) in enumerate((("ratio_with_f_retail", GREY_MARK), ("ratio_with_f_mattress", P_BLUE))):
            val = num(v[b][col])
            by = y + j * (bh + 0.04)
            hbar(s, x0, by, val * scale, bh, color)
            if j == 1:      # long bars: label inside the end, clear of the reference line
                text(s, x0, by - 0.02, val * scale - 0.1, 0.25, f"{val:.2f}×", size=12, color=WHITE, bold=True,
                     align="r")
            else:
                text(s, x0 + val * scale + 0.1, by - 0.02, 0.8, 0.25, f"{val:.2f}×", size=12, color=INK)
    bottom = y0 + 3 * pitch - 0.1
    line(s, x0, y0 - 0.12, x0, bottom, INK, 0.75)
    ref = x0 + 1.0 * scale
    line(s, ref, y0 - 0.12, ref, bottom, NAVY, 1.5)
    text(s, ref + 0.08, y0 - 0.4, 2.0, 0.25, "1.0 = Similarweb", size=11, color=NAVY, bold=True)
    text(s, 9.9, 4.95, R - 9.9, 1.7, [
        ("Walmart's factor under-counts the mattress sites **2–3×**.", {"after": 8}),
        "The mattress factor matches each site within **0.89–1.27×**."], size=13, color=INK, spacing=1.1)


def slide_hijack(prs, d):
    s = content_slide(prs, 6, "Attribution hijacking · Walmart, 6,449 clicks",
                      "13–24% of clicks take 52–79% of affiliate orders", (
        "Walmart has the volume to test the indicators. Flagged clicks are clicks without a landing, clicks fired "
        "while the shopper was already in the cart or on the site, and clicks from a publisher-bought search ad. "
        "They are 13–24% of clicks but take 52–79% of the affiliate-credited orders, depending on how strict the "
        "look-back window is, from 2 to 30 minutes. Clicks fired after the shopper had already viewed the cart "
        "convert at 13%, against 0.4% for clicks with no signal, and the order follows a median 2.3 minutes "
        "later: these clicks close sales that were already happening. Mechanisms: 258 clicks fired from "
        "walmart.com itself a median 2 seconds after a walmart.com page, with no publisher page in between; "
        "price-comparison redirects (rd.bizrate.com, 461 flagged clicks); and coupon and cash-back extensions "
        "(Capital One Shopping, Slickdeals, Rakuten)."))
    text(s, L, 1.65, 7, 0.26, "Share of Walmart affiliate clicks flagged, and the orders they take", size=12,
         color=MUTED, bold=True)
    legend(s, L, 1.98, [("Clicks flagged", GREY_MARK), ("Affiliate orders they take", P_ORANGE)])
    x0, scale, y0, pitch, bh = 2.6, 0.048, 2.65, 1.12, 0.3
    for i, (label, key) in enumerate((("30-min look-back", "30 min (base)"), ("10-min look-back", "10 min"),
                                      ("2-min look-back", "2 min"))):
        r = d["sens"][("Walmart", key)]
        y = y0 + i * pitch
        text(s, L, y + 0.17, 1.95, 0.3, label, size=14, color=INK)
        for j, (col, color) in enumerate((("pct_clicks_strong", GREY_MARK), ("pct_orders_from_strong", P_ORANGE))):
            val = num(r[col])
            by = y + j * (bh + 0.06)
            hbar(s, x0, by, val * scale, bh, color)
            text(s, x0 + val * scale + 0.1, by + 0.01, 0.9, 0.28, f"{val:.0f}%", size=14, color=INK, bold=j == 1)
    line(s, x0, y0 - 0.15, x0, y0 + 2 * pitch + 0.8, INK, 0.75)

    inj, clean = d["signal"]["Injected at cart/checkout"], d["signal"]["No hijack indicator"]
    s30 = d["sens"][("Walmart", "30 min (base)")]
    tx, tw = 8.15, R - 8.15
    box(s, tx, 1.65, tw, 2.45, fill=PANEL)
    dot(s, tx + 0.3, 1.98, P_ORANGE)
    text(s, tx + 0.55, 1.92, tw - 0.8, 0.28, "Clicks fired after the cart", size=12, color=MUTED, bold=True)
    text(s, tx + 0.3, 2.27, tw - 0.6, 0.75, f"{r0(inj['cr_pct'])}% vs {num(clean['cr_pct']):.1f}%", size=40,
         color=NAVY, bold=True)
    text(s, tx + 0.3, 3.05, tw - 0.6, 0.3, "conversion, vs clicks with no signal", size=14, color=INK, bold=True)
    text(s, tx + 0.3, 3.48, tw - 0.6, 0.3,
         f"The order follows a median {num(s30['median_min_to_order_checkout']):.1f} min later", size=12.5,
         color=MUTED)
    text(s, tx, 4.4, tw, 0.3, "How the credit is taken", size=14, color=NAVY, bold=True)
    for j, item in enumerate(("Silent redirects from walmart.com itself", "Price-comparison redirects (Bizrate)",
                              "Coupon and cash-back extensions")):
        y = 4.85 + j * 0.46
        dot(s, tx + 0.02, y + 0.07, P_ORANGE, 0.14)
        text(s, tx + 0.3, y, tw - 0.3, 0.3, item, size=14, color=INK)
    text(s, L, 6.4, CW, 0.3,
         "Flagged: a click without a landing, fired at the cart or while already on the site, or from a "
         "publisher-bought search ad.", size=12, color=MUTED)


def slide_incrementality(prs, d):
    su = d["incr_sum"]
    risk = d["risk"]["Injected at cart/checkout (tested in this step)"]
    saatva = d["risk"]["Per 10% of affiliate orders hijacked"]
    max_incr = 100 * (1 - 1 / num(su["ratio_hi95"]))
    s = content_slide(prs, 7, "Attribution hijacking · is the click incremental?",
                      "A click fired at the cart adds no orders", (
        "The obvious objection to slide 6: shoppers in the cart convert at a high rate anyway, so of course these "
        "clicks convert. That is the point, and it can be tested. Take every US Walmart shopper at the moment they "
        "first view the cart, and separately the checkout. The stage is fixed before any click, and shoppers an "
        "affiliate brought to the cart are left out. Then compare those who got an affiliate click afterwards with "
        "those who did not. At the cart, "
        f"{d['incr'][('cart', True)]['order_rate_pct']}% vs {d['incr'][('cart', False)]['order_rate_pct']}% order "
        "within two hours; at the checkout, "
        f"{d['incr'][('checkout', True)]['order_rate_pct']}% vs {d['incr'][('checkout', False)]['order_rate_pct']}%. "
        f"Across the {su['injected_users']} shoppers who got a click, {su['observed_orders']} ordered; "
        f"{su['expected_orders_without_click']} would have without it. The interval is wide (ratio "
        f"{su['ratio_lo95']}–{su['ratio_hi95']}), so at most about {max_incr:.0f}% of these orders could be "
        "incremental, and the best estimate is none. The design favours the click, since a shopper who got one "
        "stayed on the site at least until it fired. Clicks fired at the cart carry half of Walmart's "
        "affiliate-credited orders. At an average order of $100–125 and 1–4% commission, that is "
        f"${risk['commission_per_year_lo_musd']}M–{risk['commission_per_year_hi_musd']}M a year paid for sales that "
        "were already happening. Saatva's panel has no orders to measure its share, so the Saatva figure is per 10% "
        "of orders hijacked: about $860 per order and 3–10% commission."))
    text(s, L, 1.65, 7, 0.26, "Walmart shoppers who order within 2 hours, by the stage already reached", size=12,
         color=MUTED, bold=True)
    legend(s, L, 1.98, [("No affiliate click", GREY_MARK), ("Affiliate click fired afterwards", P_ORANGE)])
    x0, scale, y0, pitch, bh = 2.6, 0.048, 2.65, 1.55, 0.42
    for i, (label, stage) in enumerate((("Viewed the cart", "cart"), ("Reached checkout", "checkout"))):
        y = y0 + i * pitch
        text(s, L, y + 0.3, 1.95, 0.3, label, size=14, color=INK)
        for j, (treated, color) in enumerate(((False, GREY_MARK), (True, P_ORANGE))):
            r = d["incr"][(stage, treated)]
            val = num(r["order_rate_pct"])
            by = y + j * (bh + 0.06)
            hbar(s, x0, by, val * scale, bh, color)
            text(s, x0 + val * scale + 0.1, by + 0.06, 1.75, 0.3,
                 f"{val:.0f}%   (n = {int(num(r['users'])):,})", size=13, color=INK, bold=treated)
    line(s, x0, y0 - 0.15, x0, y0 + pitch + 2 * bh + 0.25, INK, 0.75)
    text(s, L, 5.95, 7.2, 0.6,
         "Stage fixed at the first cart or checkout view, before any click. Shoppers an affiliate brought to the "
         "cart are excluded.", size=12, color=MUTED, spacing=1.05)

    tx, tw = 8.15, R - 8.15
    box(s, tx, 1.65, tw, 2.35, fill=PANEL)
    dot(s, tx + 0.3, 1.98, P_ORANGE)
    text(s, tx + 0.55, 1.92, tw - 0.8, 0.28, f"{su['injected_users']} shoppers who got a click", size=12,
         color=MUTED, bold=True)
    text(s, tx + 0.3, 2.27, tw - 0.6, 0.75, f"{su['observed_orders']} vs {su['expected_orders_without_click']}",
         size=40, color=NAVY, bold=True)
    text(s, tx + 0.3, 3.05, tw - 0.6, 0.3, "orders, vs expected without the click", size=14, color=INK, bold=True)
    text(s, tx + 0.3, 3.45, tw - 0.6, 0.3, f"At most ~{max_incr:.0f}% incremental (95% upper bound)", size=12.5,
         color=MUTED)
    box(s, tx, 4.2, tw, 2.55, fill=ORANGE_TINT)
    text(s, tx + 0.3, 4.42, tw - 0.6, 0.28, "Commission on clicks fired at the cart", size=12, color=MUTED, bold=True)
    text(s, tx + 0.3, 4.75, tw - 0.6, 0.7,
         f"${float(risk['commission_per_year_lo_musd']):.0f}–{float(risk['commission_per_year_hi_musd']):.0f}M",
         size=36, color=NAVY, bold=True)
    text(s, tx + 0.3, 5.45, tw - 0.6, 0.3, "a year at Walmart (half its affiliate orders)", size=14, color=INK, bold=True)
    text(s, tx + 0.3, 5.85, tw - 0.6, 0.8,
         f"Saatva: ${float(saatva['commission_per_year_lo_musd']) * 1000:.0f}K–"
         f"{saatva['commission_per_year_hi_musd']}M a year for every 10% of affiliate orders hijacked",
         size=12.5, color=MUTED, spacing=1.05)


def slide_cases(prs, d):
    s = content_slide(prs, 8, "Attribution hijacking · Saatva", "The same patterns already appear at Saatva", (
        "Three cases from Saatva's own clicks. One: a 'new tab' browser extension (newtab.club, via tatrck.com) "
        "fired a Partnerize click for Saatva (publisher camref 1011laqH9), but saatva.com never loaded; the user "
        "was on Sleep Number at the time. If they buy from Saatva within the cookie window, the extension is paid: "
        "that is cookie stuffing. Two: brandxemail is listed as an email publisher, but its click came from a "
        "Google ad (gad_source=1) and landed on /sale with an auto-applied coupon: a question for the PPC terms. "
        "Three: TrafficPoint, a paid-search listicle, sent one user to six brands within a minute. The user "
        "really browsed, so this is not stuffing, but nine minutes later they came back through a Google Shopping "
        "ad, likely Saatva's own, so Saatva may pay twice. The indicators should trigger a review, not an "
        "automatic penalty."))
    cases = [
        ("Cookie stuffing", P_ORANGE, WHITE,
         ["\"New tab\" browser extension", "Partnerize click registered", "saatva.com never loads"],
         "A commission without a visit", "Reconcile clicks with landings"),
        ("Undeclared paid search", ORANGE_TINT, ORANGE_TEXT,
         ["Google ad (gad_source=1)", "brandxemail, listed as \"email\"", "saatva.com/sale + auto-coupon"],
         "Paid search under an email listing", "Check it against the PPC terms"),
        ("Review before acting", BLUE_TINT, P_DEEP,
         ["Search ad → TrafficPoint listicle", "6 brands opened in ~1 minute", "Back 9 min later via a Shopping ad"],
         "Real browsing, but Saatva may pay twice", "De-duplicate with paid search"),
    ]
    cw, gap = (CW - 2 * 0.3) / 3, 0.3
    for i, (tag, tfill, tcolor, steps, verdict, action) in enumerate(cases):
        x = L + i * (cw + gap)
        box(s, x, 1.65, cw, 5.1, fill=PANEL)
        pill(s, x + 0.3, 1.92, 0.15 + 0.11 * len(tag), tag, tfill, tcolor, size=12)
        for j, st in enumerate(steps):
            y = 2.6 + j * 0.86
            last = j == len(steps) - 1
            stuffed = last and i == 0
            label_box(s, x + 0.3, y, cw - 0.6, 0.56, st, ORANGE_TINT if stuffed else WHITE, size=13,
                      color=ORANGE_TEXT if stuffed else INK, bold=last, align="c",
                      line=P_ORANGE if stuffed else GRID, line_w=1.25 if stuffed else 0.75,
                      shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.15)
            if not last:
                line(s, x + cw / 2, y + 0.6, x + cw / 2, y + 0.82, MUTED, 1.25, arrow=True)
        text(s, x + 0.3, 5.35, cw - 0.6, 0.62, verdict, size=15, color=NAVY, bold=True, spacing=1.05)
        text(s, x + 0.3, 6.05, cw - 0.6, 0.5, f"→  {action}", size=13, color=INK)


def slide_recommendations(prs, d):
    s = content_slide(prs, 9, "Recommendations", "Pay for the assist, not the last touch", (
        "Grow: recruit the partner types the rivals already get traffic from: review sites like Mattress Clarity, "
        "buyer's guides like buyersguide.org, and HSA/FSA payment partners like Truemed. Give each publisher its "
        "own coupon code: today Mattress Nerd and TrafficPoint landings auto-apply the same code. Tier "
        "commissions: more for content and new customers, less for coupon clicks and for clicks after a cart "
        "exists. Protect: start by reconciling Partnerize click logs with saatva.com landings, because a click id "
        "that never lands is direct evidence. Then no commission overwrite after a cart exists, extension "
        "stand-down, a PPC and trademark policy, and weekly per-publisher monitoring of six indicators, with "
        "payouts held on flagged orders. Next step: the same pipeline on 90 days of data and on Saatva's own "
        "Partnerize logs, to size the impact."))
    cols = [
        ("Grow the program", S_MARK, [
            ("Recruit review and HSA/FSA partners",
             "Mattress Clarity, buyersguide.org and Truemed send rivals traffic; none seen at Saatva"),
            ("Give each publisher its own coupon code",
             "One code is shared today, so a sale can't be traced to its partner"),
            ("Tier commissions by the value of the click",
             "Pay less for coupon clicks and for clicks after a cart exists"),
        ]),
        ("Stop paying for taken credit", P_ORANGE, [
            ("Reconcile clicks with saatva.com landings",
             "A click that never lands is proof, with no threshold to tune"),
            ("No overwrite once a cart exists",
             "Cart-stage clicks add no orders (slide 7); plus extension stand-down, PPC policy"),
            ("Monitor every publisher (built: next slide)",
             "Hold payouts on flagged orders; validate on reversals"),
        ]),
    ]
    pw, gap = (CW - 0.5) / 2, 0.5
    for i, (head, color, items) in enumerate(cols):
        x = L + i * (pw + gap)
        dot(s, x, 1.8, color, 0.2)
        text(s, x + 0.35, 1.7, pw - 0.4, 0.38, head, size=19, color=NAVY, bold=True)
        for j, (title, detail) in enumerate(items):
            y = 2.45 + j * 1.13
            number_badge(s, x, y, j + 1, color)
            text(s, x + 0.65, y - 0.01, pw - 0.7, 0.32, title, size=16, color=INK, bold=True)
            text(s, x + 0.65, y + 0.37, pw - 0.7, 0.55, detail, size=13, color=MUTED, spacing=1.05)
    label_box(s, L, 5.98, CW, 0.68,
              "**Next:** run the same pipeline on 90 days of data and on Saatva's Partnerize logs, to size the impact",
              NAVY, size=15, color=WHITE, accent=P_ORANGE, margin=0.3)


def slide_monitor(prs, d):
    su = d["incr_sum"]
    s = content_slide(prs, 10, "From analysis to monitoring", "The indicators, built into a publisher monitor", (
        "The recommendations need a tool a partner manager can use every week, so the pipeline also builds one: "
        "dashboard/publisher_risk_monitor.html, a single file that opens in any browser. It re-scores every affiliate "
        "click under the chosen look-back window, so the 2-to-30-minute sensitivity is a click, not a footnote. It "
        "ranks publishers by the commission paid on their flagged orders, with a Hold, Review or OK status, and the "
        "average order and commission are inputs. Every number can be traced to the journey behind a click. The strip "
        "at the bottom is one of them: a shopper browsed Walmart, reached checkout, and two seconds after a Bizrate "
        "redirect an Impact click 'landed' on the order confirmation page, in the same second as the order. The "
        "publisher, impact:150372, has 32 credited orders in the panel, 78% of them from flagged clicks. The same view "
        "works for Saatva today; with Partnerize's own click and order logs instead of a one-day panel, the counts "
        "behind each status would be complete."))
    img = os.path.join(ROOT, "deck", "img")
    ow = 5.9
    s.shapes.add_picture(os.path.join(img, "dashboard_overview.png"), Inches(L), Inches(1.6), width=Inches(ow))
    box(s, L, 1.6, ow, ow * 1720 / 2560, line=GRID)
    tx, tw = L + ow + 0.5, R - (L + ow + 0.5)
    items = [
        ("Any look-back, one click", "Every click re-scored at 2, 10 or 30 minutes; the sensitivity test becomes a control"),
        ("Ranked by money, with a status", "Hold, Review or OK per publisher, by commission on flagged orders; AOV and rate are inputs"),
        ("Every flag has a journey", "The sites before and after each click, so a reviewer sees the evidence, not a score"),
    ]
    for j, (head, body) in enumerate(items):
        y = 1.7 + j * 1.25
        number_badge(s, tx, y, j + 1, P_ORANGE, d=0.36, size=12)
        text(s, tx + 0.52, y - 0.02, tw - 0.52, 0.32, head, size=15, color=NAVY, bold=True)
        text(s, tx + 0.52, y + 0.33, tw - 0.52, 0.75, body, size=12.5, color=MUTED, spacing=1.05)
    text(s, L, 5.72, CW, 0.28, "One of impact:150372's 32 orders: the click \"lands\" on the order confirmation page",
         size=12, color=MUTED, bold=True)
    s.shapes.add_picture(os.path.join(img, "dashboard_journey.png"), Inches(L), Inches(6.04), width=Inches(CW * 0.85))


def appendix_results(prs, d):
    s = content_slide(prs, 11, "Backup", "Results by brand",
                      "Full results table. Conservative estimates use the Walmart-calibrated factor for the mattress "
                      "brands and the population ratio for Walmart.")
    c = d["comp"]
    rows = [["Brand", "Network", "Panel visits", "Visits from affiliate", "Panel affiliate clicks",
             "Est. US clicks / day", "95% CI", "Conservative", "Est. US converting clicks / day"]]
    for b in ("Saatva", "Nectar", "Helix", "DreamCloud", "Walmart"):
        r = c[b]
        conv = (f"{k(r['est_us_converted_clicks'])} ({pct(r['pct_clicks_converting'], 2)})" if b == "Walmart" else
                f"{k(r['est_us_converted_clicks_benchmark_lo'])}–{k(r['est_us_converted_clicks_benchmark_hi'])} ²")
        rows.append([b, "Impact" if b == "Walmart" else r["networks"], f"{num(r['panel_visits']):,.0f}",
                     pct(r["pct_visits_from_affiliate"]),
                     f"{num(r['panel_affiliate_clicks']):,.0f}" + (" ¹" if b == "Saatva" else ""),
                     k(r["est_us_affiliate_clicks"]),
                     f"{k(r['est_us_affiliate_clicks_lo95'])}–{k(r['est_us_affiliate_clicks_hi95'])}",
                     k(r["est_us_affiliate_clicks_alt"]), conv])
    table(s, L, 1.7, [1.35, 1.15, 1.05, 1.2, 1.2, 1.35, 1.5, 1.3, 2.03], rows, [0.6] + [0.45] * 5, size=12,
          header_size=11, aligns=["l", "l", "r", "r", "r", "r", "r", "r", "r"], bold_cols=(0, 5),
          fills=[None, BRONZE_TINT, None, None, None, None])
    text(s, L, 4.75, CW, 1.6, [
        ("¹ Five landings plus one Partnerize click that never loaded the site.", {"after": 3}),
        ("² No mattress order, registration or financing application followed an affiliate click that day; the "
         "range applies a 0.5–2% category conversion rate.", {"after": 3}),
        ("Conservative: the Walmart-calibrated factor for the mattress brands, the population ratio for Walmart. "
         "95% CI: Poisson sampling error of the panel count only.", {"after": 10}),
        "Sources: Similarweb website pages (Aug 2026); DataReportal, Digital 2026 (324M US internet users); "
        "Grips Intelligence retailer pages (mattress conversion rates)."], size=11.5, color=MUTED, spacing=1.1)


def appendix_data(prs, d):
    s = content_slide(prs, 12, "Backup", "Data validation",
                      "Each check, what it found, and how the pipeline handles it.")
    dq = d["dq"]
    dup = 100 * num(dq["duplicate_rows"]) / num(dq["rows"])
    rows = [
        ["Check", "Finding", "Handling"],
        ["Period", "One day only: 1 May 2026, 00:00–23:59 UTC", "Daily estimates; same-day attribution"],
        ["Double-recorded events", f"{dup:.1f}% of rows repeat the same user, second and URL", "Deduplicated"],
        ["Mirror user IDs", "Some people recorded under two USER_IDs, one a partial copy; inflated brand visits "
         "14–28% and orders 20%", "IDs sharing ≥3 identical events merged (2,426 IDs)"],
        ["Non-page rows", "iframes and tags appear as rows (sgtm.saatva.com, Shopify pixels)",
         "Visits use main-site pages only"],
        ["Sessions", "~2.5 parallel SESSION_IDs per user per day, one per tab", "Analysis per person"],
        ["Country", "No country field", "Non-US if ≥20% of events on non-US country domains: 88.5% US"],
        ["Hourly profile", "Step changes at 12:00 and 18:00 UTC, likely a collection artefact", "Daily totals only"],
    ]
    table(s, L, 1.7, [2.4, 5.4, 4.33], rows, [0.45] + [0.6] * 7, size=12, header_size=11,
          fills=[None, None, None, BRONZE_TINT, None, None, None, None])


def appendix_indicators(prs, d):
    s = content_slide(prs, 13, "Backup", "Hijacking indicators and Walmart outcomes",
                      "Each click counts once, under its first-ranked indicator, so the Walmart columns add up to "
                      "all 6,449 clicks. Strong indicators are highlighted.")
    sig = d["signal"]
    defs = [
        ("Click without landing", "Network click, but the brand's site never loads", "Strong",
         "Click without landing (stuffing)"),
        ("Injected at cart / checkout", "In the brand's cart or checkout in the 30 min before", "Strong",
         "Injected at cart/checkout"),
        ("Already on site", "On the brand's site, untagged, in the 30 min before", "Strong",
         "User already on brand site"),
        ("Publisher-bought search ad", "Google/Bing ad click id on the affiliate landing", "Strong",
         "Publisher-bought search ad"),
        ("Brand search before", "A search for the brand within 60 s before", "Medium", "Brand search just before"),
        ("Coupon / cash-back before", "A coupon or cash-back site or extension within 60 s", "Medium",
         "Coupon/cash-back just before"),
        ("Multi-brand burst", "2+ other advertisers within ±2 min, no engagement", "Review",
         "Multi-brand burst (review)"),
        ("No visible referrer", "No activity in the 30 min before", "Weak", "No visible referrer (weak)"),
        ("No indicator", "", "", "No hijack indicator"),
    ]
    rows = [["Indicator", "Definition", "Tier", "Share of clicks", "Conv. rate", "Share of orders"]]
    fills = [None]
    for name, desc, tier, key in defs:
        r = sig.get(key)
        rows.append([name, desc, tier] + ([pct(r["pct_of_clicks"]), pct(r["cr_pct"]), pct(r["pct_of_converted_clicks"])]
                                          if r else ["—", "—", "—"]))
        fills.append(ORANGE_TINT if tier == "Strong" else None)
    table(s, L, 1.65, [2.75, 4.6, 1.0, 1.3, 1.15, 1.33], rows, [0.42] + [0.47] * 9, size=12, header_size=11,
          aligns=["l", "l", "l", "r", "r", "r"], fills=fills)
    text(s, L, 6.55, CW, 0.3, f"Code, SQL and result tables: **{REPO}**", size=11.5, color=MUTED, accent=P_DEEP)


# Theme and package fixes -------------------------------------------------------------
def set_theme(prs):
    """Theme fonts and colours, so text and shapes added later in Google Slides match."""
    part = prs.slide_master.part.part_related_by(RT.THEME)
    root = etree.fromstring(part.blob)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    root.find(".//a:majorFont/a:latin", ns).set("typeface", TITLE_FONT)
    root.find(".//a:minorFont/a:latin", ns).set("typeface", BODY_FONT)
    scheme = root.find(".//a:clrScheme", ns)
    colours = {"dk2": NAVY, "lt2": PANEL, "accent1": P_BLUE, "accent2": P_ORANGE, "accent3": S_MARK,
               "accent4": P_DEEP, "accent5": MUTED, "accent6": GREY_MARK}
    for name, value in colours.items():
        el = scheme.find(f"a:{name}", ns)
        for child in list(el):
            el.remove(child)
        etree.SubElement(el, qn("a:srgbClr")).set("val", value)
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def register_notes_master(prs):
    """python-pptx links the notes master but doesn't list it in presentation.xml. PowerPoint
    tolerates that; Keynote and Quick Look hang on open. List it, as PowerPoint does."""
    pres = prs.part._element
    if pres.find(qn("p:notesMasterIdLst")) is None:
        rid = next(r.rId for r in prs.part.rels.values() if r.reltype == RT.NOTES_MASTER)
        lst = etree.Element(qn("p:notesMasterIdLst"))
        etree.SubElement(lst, qn("p:notesMasterId")).set(qn("r:id"), rid)
        pres.find(qn("p:sldMasterIdLst")).addnext(lst)
    pres.find(qn("p:sldSz")).attrib.pop("type", None)      # the template says 4:3


def main():
    d = load()
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    set_theme(prs)
    for build in (slide_title, slide_answer, slide_share, slide_volume, slide_method, slide_hijack, slide_incrementality,
                  slide_cases,
                  slide_recommendations, slide_monitor, appendix_results, appendix_data, appendix_indicators):
        build(prs, d)
    register_notes_master(prs)
    prs.save(OUT)
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(prs.slides)} slides")


if __name__ == "__main__":
    main()
