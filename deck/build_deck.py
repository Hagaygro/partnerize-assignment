"""Build the presentation deck from the pipeline outputs.

Usage:
    .venv/bin/python deck/build_deck.py        # -> deck/saatva_affiliate_analysis.pptx

The numbers come from outputs/*.csv. The case studies and the external benchmarks are
written into the text. The slides use plain shapes, text boxes and tables, with no
embedded chart objects, so the file imports into Google Slides with its layout intact
and stays editable there. Fonts are Georgia (titles) and Arial (text), which Google
Slides and Keynote both have.

Palette: Partnerize's orange and blues frame the deck. Saatva's bronze marks the client.
"""
import csv
import math
import os

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE
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
P_BLUE = "368EF8"          # Partnerize blue: the affiliate channel, clicks with no signal
P_ORANGE = "FF9438"        # Partnerize orange: accents, hijack signals
ORANGE_TEXT = "C9620E"     # the orange, darkened for text on white
ORANGE_TINT = "FFF1E5"
S_BRONZE = "C19678"        # Saatva bronze: the client
BRONZE_TEXT = "9A7152"     # the bronze, darkened for text on white
BRONZE_TINT = "F6EFE8"
BLUE_TINT = "EAF2FE"
INK = "1E2833"
MUTED = "647282"
GRID = "D6DDE5"
PANEL = "F3F6F9"
GREY_BAR = "B7C1CC"
PAID = "6F8196"
OTHER = "AEBBC8"
UNTAGGED = "E2E7ED"
WHITE = "FFFFFF"

TITLE_FONT = "Georgia"
BODY_FONT = "Arial"

W, H = 13.333, 7.5
L, R = 0.6, 12.733         # content edges
CW = R - L
TOP = 1.85                 # where the body starts, below a two-line title

FOOTER = "Saatva affiliate analysis  ·  Partnerize home assignment  ·  Hagay Gross"
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
        "signal": [r for r in rows("signal_summary") if r["brand"] == "Walmart"],
        "valid": {r["brand"]: r for r in rows("scaling_validation")},
        "scaling": rows("scaling")[0],
        "dq": rows("dq_profile")[0],
        "sources": [r for r in rows("flagged_click_sources") if r["brand"] == "Walmart"],
    }


def num(v):
    return float(v) if v not in ("", None) else 0.0


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


def _runs(p, s, size, color, font, bold, italic, accent, accent_bold, spc):
    """Add `s` to paragraph `p`; **marked** parts are bold and, with `accent`, coloured."""
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


def _bullet(p, color, indent):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(Inches(indent)))
    pPr.set("indent", str(-Inches(indent)))
    clr = etree.SubElement(etree.SubElement(pPr, qn("a:buClr")), qn("a:srgbClr"))
    clr.set("val", color)
    etree.SubElement(pPr, qn("a:buFont")).set("typeface", BODY_FONT)
    etree.SubElement(pPr, qn("a:buChar")).set("char", "•")


def fill_text(tf, paras, size=12, color=INK, font=BODY_FONT, bold=False, italic=False, align="l",
              spacing=1.1, after=0, bullet=False, accent=None, accent_bold=True, spc=None, indent=0.17):
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
        if o.get("before"):
            p.space_before = Pt(o["before"])
        _runs(p, para, o.get("size", size), o.get("color", color), o.get("font", font),
              o.get("bold", bold), o.get("italic", italic), o.get("accent", accent),
              o.get("accent_bold", accent_bold), o.get("spc", spc))
        if o.get("bullet", bullet):
            _bullet(p, o.get("bullet_color", GREY_BAR), o.get("indent", indent))
        elif o.get("margin"):
            p._p.get_or_add_pPr().set("marL", str(Inches(o["margin"])))


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


def label_box(slide, x, y, w, h, paras, fill, anchor="m", margin=0.06, shape=MSO_SHAPE.RECTANGLE,
              radius=None, line=None, **kw):
    """A filled shape with text inside."""
    s = box(slide, x, y, w, h, fill=fill, shape=shape, radius=radius, line=line)
    tf = s.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = Inches(margin)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = ANCHOR[anchor]
    fill_text(tf, paras, **kw)
    return s


def pill(slide, x, y, w, label, fill, color, h=0.26, size=9):
    return label_box(slide, x, y, w, h, label, fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5,
                     margin=0.03, size=size, color=color, bold=True, align="c")


def line(slide, x1, y1, x2, y2, color=GRID, w=0.75, dash=False, arrow=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    _plain(c)
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(w)
    if dash:
        c.line.dash_style = MSO_LINE.DASH
    if arrow:
        end = etree.SubElement(c.line._get_or_add_ln(), qn("a:tailEnd"))
        end.set("type", "triangle")
        end.set("w", "med")
        end.set("len", "med")
    return c


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


def _cell_borders(cell, bottom=None, top=None, w=0.75):
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        old = tcPr.find(qn(tag))
        if old is not None:
            tcPr.remove(old)
    for i, (tag, color) in enumerate((("a:lnL", None), ("a:lnR", None), ("a:lnT", top), ("a:lnB", bottom))):
        ln = etree.Element(qn(tag))
        ln.set("w", str(Pt(w)) if color else "0")
        if color:
            etree.SubElement(etree.SubElement(ln, qn("a:solidFill")), qn("a:srgbClr")).set("val", color)
        else:
            etree.SubElement(ln, qn("a:noFill"))
        tcPr.insert(i, ln)


def table(slide, x, y, widths, rows, heights, size=10.5, header_size=10, header_fill=NAVY,
          fills=None, aligns=None, bold_cols=(0,), colors=None):
    """rows[0] is the header. fills/colors: per-row overrides (None keeps the default)."""
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
            c.fill.fore_color.rgb = rgb(header_fill if head else (fills[i] if fills and fills[i] else WHITE))
            color = WHITE if head else (colors[i] if colors and colors[i] else INK)
            fill_text(c.text_frame, val, size=header_size if head else size, color=color,
                      bold=head or j in bold_cols, align=aligns[j] if aligns else "l", spacing=1.0)
            _cell_borders(c, bottom=None if head else GRID)
    return tbl


# Slide frame -----------------------------------------------------------------------
def content_slide(prs, n, kicker, title, notes):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    box(s, 0, 0, W, 0.07, fill=NAVY)
    box(s, 0, 0, L + 1.6, 0.07, fill=P_ORANGE)
    text(s, L, 0.4, 9, 0.28, kicker.upper(), size=10.5, color=ORANGE_TEXT, bold=True, spc=150)
    text(s, L, 0.7, CW, 1.05, title, size=24, color=NAVY, font=TITLE_FONT, spacing=1.0)
    line(s, L, 7.0, R, 7.0, GRID, 0.5)
    text(s, L, 7.07, 9, 0.25, FOOTER, size=8.5, color=MUTED)
    box(s, R - 0.47, 7.115, 0.13, 0.13, fill=P_ORANGE, shape=MSO_SHAPE.OVAL)
    box(s, R - 0.39, 7.115, 0.13, 0.13, fill=P_BLUE, shape=MSO_SHAPE.OVAL)
    text(s, R - 0.22, 7.07, 0.22, 0.25, str(n), size=8.5, color=MUTED, align="r")
    s.notes_slide.notes_text_frame.text = notes
    return s


def card_header(s, x, y, w, title, color, size=13):
    box(s, x, y + 0.04, 0.07, 0.24, fill=color)
    text(s, x + 0.17, y, w - 0.17, 0.32, title, size=size, color=NAVY, bold=True)


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
         size=42, color=WHITE, font=TITLE_FONT, accent=S_BRONZE, accent_bold=False, spacing=1.0)
    text(s, 0.8, 3.85, 8.0, 0.75,
         "US clicks and conversions  ·  Growth levers  ·  Attribution hijacking",
         size=17, color="C9D6E3", spacing=1.15)
    box(s, 0.8, 5.5, 0.9, 0.05, fill=P_ORANGE)
    text(s, 0.8, 5.72, 8, 0.32, "Hagay Gross", size=16, color=WHITE, bold=True)
    dq = d["dq"]
    text(s, 0.8, 6.08, 9, 0.3,
         f"October 2026  ·  Data: US clickstream panel, 1 May 2026 "
         f"({num(dq['rows']) / 1e6:.1f}M events, {num(dq['users']) / 1e3:.0f}K users)",
         size=11.5, color="9FB3C8")
    s.notes_slide.notes_text_frame.text = (
        "Three questions for Saatva: how its US affiliate program compares with Nectar, Helix, "
        "DreamCloud and Walmart; how to grow it; and how to control attribution hijacking. "
        "The data is a one-day clickstream panel.")


def slide_summary(prs, d):
    s = content_slide(prs, 2, "Executive summary",
                      "Affiliate is already Saatva's edge; the next lever is click quality, not volume",
                      "Saatva's affiliate channel is already its strongest: 16% of visits start with an affiliate "
                      "click, the highest of the four mattress brands, and Similarweb independently ranks affiliate "
                      "as Saatva's #1 channel. The volume estimate (~16.7K US clicks a day) has a wide interval "
                      "because it rests on six panel clicks. The bigger lever is click quality: at Walmart, where "
                      "the volume allows a test, a minority of flagged clicks takes most of the credited orders, "
                      "and Saatva's own clicks already show cookie stuffing and undeclared paid search.")
    c = d["comp"]
    sa = c["Saatva"]
    rivals = [num(c[b]["pct_visits_from_affiliate"]) for b in ("Nectar", "Helix", "DreamCloud")]
    s30, s2 = d["sens"][("Walmart", "30 min (base)")], d["sens"][("Walmart", "2 min")]
    cards = [
        (f"{num(sa['pct_visits_from_affiliate']):.0f}%", BRONZE_TEXT, S_BRONZE,
         "of Saatva's visits start with an affiliate click",
         f"vs {min(rivals):.1f}–{max(rivals):.1f}% at Nectar, DreamCloud and Helix. Similarweb also ranks "
         "affiliate as Saatva's #1 traffic channel."),
        ("~" + k(sa["est_us_affiliate_clicks"]), BRONZE_TEXT, S_BRONZE,
         "US affiliate clicks a day (estimate)",
         f"95% CI {k(sa['est_us_affiliate_clicks_lo95'])}–{k(sa['est_us_affiliate_clicks_hi95'])}; "
         f"conservative {k(sa['est_us_affiliate_clicks_alt'])}. Scaled from "
         f"{int(num(sa['panel_affiliate_clicks']))} clicks in the panel."),
        (f"{k(sa['est_us_converted_clicks_benchmark_lo'])}–{k(sa['est_us_converted_clicks_benchmark_hi'])}",
         BRONZE_TEXT, S_BRONZE, "converting clicks a day (estimate)",
         "At a 0.5–2% category conversion rate: no mattress order followed an affiliate click "
         "in the panel day."),
        (f"{num(s2['pct_orders_from_strong']):.0f}–{num(s30['pct_orders_from_strong']):.0f}%",
         ORANGE_TEXT, P_ORANGE, "of Walmart's affiliate-credited orders",
         f"come from the {num(s2['pct_clicks_strong']):.0f}–{num(s30['pct_clicks_strong']):.0f}% of "
         "clicks that carry a hijack signal."),
    ]
    cw, gap, y, h = 2.88, 0.205, TOP, 1.98
    for i, (big, big_color, bar, label, note) in enumerate(cards):
        x = L + i * (cw + gap)
        box(s, x, y, cw, h, fill=PANEL)
        box(s, x, y, cw, 0.06, fill=bar)
        text(s, x + 0.2, y + 0.2, cw - 0.4, 0.6, big, size=32, color=big_color, font=TITLE_FONT)
        text(s, x + 0.2, y + 0.84, cw - 0.4, 0.46, label, size=12, color=INK, bold=True, spacing=1.0)
        text(s, x + 0.2, y + 1.32, cw - 0.4, 0.62, note, size=9.5, color=MUTED, spacing=1.05)
    text(s, L, 4.05, CW, 0.3,
         "One panel day cannot rank the mattress brands by volume (2–6 clicks each, overlapping intervals), "
         "so they are compared on traffic share and publisher mix.",
         size=10.5, color=MUTED, italic=True)
    cols = [
        ("Grow the program", S_BRONZE, [
            "Recruit the review, comparison and HSA/FSA partners that already send shoppers to Helix, "
            "DreamCloud and Nectar.",
            "Give each publisher its own coupon code, and tier commissions to pay for the assist, "
            "not the last touch.",
            "De-duplicate against Saatva's own paid search, and judge publishers on 30-day journeys.",
        ]),
        ("Protect it from attribution hijacking", P_ORANGE, [
            "Saatva's own data already shows **cookie stuffing**: a \"new tab\" browser extension fired a "
            "Partnerize click, and saatva.com never loaded.",
            "Block commission overwrites once a cart exists, enforce extension stand-down, and set a "
            "PPC and trademark policy.",
            "Monitor six indicators per publisher every week, and hold payouts on flagged orders.",
        ]),
    ]
    colw = (CW - 0.35) / 2
    for i, (head, color, bullets) in enumerate(cols):
        x = L + i * (colw + 0.35)
        card_header(s, x, 4.55, colw, head, color, size=14)
        text(s, x + 0.17, 5.0, colw - 0.17, 1.9, bullets, size=11.5, bullet=True, after=5, spacing=1.08)


def slide_approach(prs, d):
    s = content_slide(prs, 3, "Approach",
                      "One pass over 48.4M events, then every step runs on the 3.4% that matters",
                      "One pass selects the users who touched any of the five brands; everything after that runs "
                      "on 3.4% of the rows, so the whole pipeline takes about 30 seconds on a laptop. The "
                      "definitions come from what is visible in the URLs: Partnerize and Impact tracking "
                      "parameters, network redirect hops, and order-confirmation paths.")
    steps = [
        ("Raw panel", ["48.4M events", "784K users", "1 day: 1 May 2026"]),
        ("Brand users", ["1.64M events (3.4%)", "Users who touched a brand", "Deduplicated; mirror IDs merged"]),
        ("Measure", ["Affiliate clicks", "Visits and traffic sources", "Orders and funnel steps",
                     "Hijack indicators"]),
        ("Scale to the US", ["US users only", "Audience-calibrated factor", "95% confidence intervals"]),
        ("Stress-test", ["Indicator look-back", "30 / 10 / 2 minutes", "Similarweb cross-checks"]),
    ]
    bw, gap, y, h = 2.2, (CW - 5 * 2.2) / 4, TOP, 1.55
    for i, (head, lines) in enumerate(steps):
        x = L + i * (bw + gap)
        label_box(s, x, y, bw, 0.42, f"{i + 1}   {head}", NAVY, size=11.5, color=WHITE, bold=True, margin=0.12)
        box(s, x, y + 0.42, bw, h - 0.42, fill=PANEL)
        text(s, x + 0.12, y + 0.55, bw - 0.24, h - 0.6, lines, size=10.5, color=INK, after=2)
        if i < 4:
            line(s, x + bw + 0.03, y + h / 2, x + bw + gap - 0.03, y + h / 2, P_ORANGE, 1.5, arrow=True)
    defs = [
        ("Affiliate click",
         "A landing whose URL carries network tracking (Partnerize click_id, Impact irclickid / CIDIMP, "
         "Walmart wmlspartner), or a network redirect hop (saatva.prf.hn). De-duplicated by click id. "
         "A hop that never lands is a **click without landing**."),
        ("Conversion",
         "**Primary:** the order-confirmation page, matched on the URL path. **Broad:** an order, an account "
         "registration or a financing application (Affirm, Klarna). Cart and checkout reach are tracked as "
         "funnel steps."),
        ("Attribution",
         "The last affiliate click for the brand earlier the same day, since the data covers one day. "
         "A click keeps the credit until the user's next affiliate click for that brand."),
        ("Visits and US users",
         "A visit is a run of pageviews on the brand's site, split at 30-minute gaps; its entry URL gives the "
         "traffic source. A user is non-US if ≥20% of their events are on non-US country domains (88.5% are US)."),
    ]
    dw, dh = (CW - 0.3) / 2, 1.3
    for i, (head, body) in enumerate(defs):
        x = L + (i % 2) * (dw + 0.3)
        y0 = 3.68 + (i // 2) * (dh + 0.14)
        card_header(s, x, y0, dw, head, P_BLUE, size=12.5)
        text(s, x + 0.17, y0 + 0.38, dw - 0.17, dh - 0.38, body, size=10.5, color=INK, spacing=1.08)
    text(s, L, 6.62, CW, 0.28,
         f"DuckDB SQL  ·  10 documented steps  ·  ~30 seconds on a laptop  ·  **{REPO}**",
         size=10.5, color=MUTED, accent=P_DEEP)


def slide_data_quality(prs, d):
    s = content_slide(prs, 4, "Data validation",
                      "Validating the data changed the answer: duplicates and mirror IDs would have inflated "
                      "the results",
                      "Two issues mattered. 14.7% of rows are double-recorded, and some people appear under two "
                      "user ids, one a partial copy of the other. Without merging them, brand visits were inflated "
                      "by 14–28% and orders by 20%. The other checks set how the data can be used: one day only, "
                      "no country field, and per-tab sessions.")
    dq = d["dq"]
    dup = 100 * num(dq["duplicate_rows"]) / num(dq["rows"])
    rows = [
        ["Check", "Finding", "Handling"],
        ["Period", "One day only: 1 May 2026, 00:00–23:59 UTC", "Daily estimates; same-day attribution"],
        ["Double-recorded events", f"{dup:.1f}% of rows repeat the same user, second and URL", "Deduplicated"],
        ["Mirror user IDs", "Some people are recorded under two USER_IDs, one a partial copy of the other",
         "IDs sharing ≥3 identical events merged into one person (2,426 IDs)"],
        ["Non-page rows", "iframes and tags appear as rows (sgtm.saatva.com, Shopify pixels)",
         "Visits use main-site pages only"],
        ["Sessions", "~2.5 parallel SESSION_IDs per user per day, one per tab", "Analysis per person, not per session"],
        ["Country", "No country field", "Non-US if ≥20% of events are on non-US country domains: 88.5% US"],
        ["Hourly profile", "Step changes at 12:00 and 18:00 UTC, likely a collection artefact",
         "Daily totals only; no intraday conclusions"],
    ]
    table(s, L, TOP, [1.75, 3.65, 3.2], rows, [0.4] + [0.53] * 7, size=10.5,
          fills=[None, None, None, BRONZE_TINT, None, None, None, None])
    stats = [
        (f"{dup:.1f}%", "of rows are double-recorded: same user, second and URL"),
        ("14–28%", "of brand visits came from mirror IDs, one person under two USER_IDs"),
        ("20%", "of orders were mirror copies before the merge"),
    ]
    x, w = 9.5, R - 9.5
    for i, (big, label) in enumerate(stats):
        y = TOP + i * 1.43
        box(s, x, y, w, 1.3, fill=PANEL)
        box(s, x, y, 0.06, 1.3, fill=P_ORANGE)
        text(s, x + 0.25, y + 0.14, w - 0.4, 0.55, big, size=28, color=ORANGE_TEXT, font=TITLE_FONT)
        text(s, x + 0.25, y + 0.72, w - 0.4, 0.5, label, size=10.5, color=INK, spacing=1.05)
    text(s, L, 6.3, CW, 0.5,
         "Example: one affiliate click was recorded under two IDs. On the partial copy, the click lost "
         "the browsing that came before it, which is exactly what the hijacking indicators read.",
         size=10.5, color=MUTED, italic=True)


def slide_scaling(prs, d):
    s = content_slide(prs, 5, "Scaling to the US",
                      "A factor calibrated on the mattress audience reproduces each site's real traffic",
                      "A walmart.com-calibrated factor recovers only 35–50% of the mattress sites' traffic, "
                      "because the panel under-covers that audience. Calibrating on the mattress sites "
                      "themselves reproduces each brand within 0.89–1.27x. The Walmart factor is kept as the "
                      "conservative low end. Similarweb's latest public month is August, the Labor Day sale "
                      "season, so the mattress factor may overstate an ordinary May day somewhat.")
    sc, v = d["scaling"], d["valid"]
    text(s, L, TOP, 6.1, 0.62,
         "US estimate = panel count × **F**, where F = a site's true US visits per day ÷ the panel's US visits "
         "to it, calibrated on sites with public traffic figures (Similarweb).",
         size=12, color=INK, accent=NAVY, spacing=1.08)
    mattress = [b for b in ("Saatva", "Nectar", "DreamCloud")]
    r_lo = min(num(v[b]["ratio_with_f_retail"]) for b in mattress)
    r_hi = max(num(v[b]["ratio_with_f_retail"]) for b in mattress)
    m_lo = min(num(v[b]["ratio_with_f_mattress"]) for b in mattress)
    m_hi = max(num(v[b]["ratio_with_f_mattress"]) for b in mattress)
    anchors = [
        ("Retail anchor: walmart.com", GREY_BAR,
         f"{num(sc['walmart_us_visits_per_day']) / 1e6:.1f}M US visits a day ÷ "
         f"{num(sc['walmart_us_visits_panel']):,.0f} panel visits  →  **F_retail = {num(sc['scale_factor_retail']):,.0f}**",
         f"Used for Walmart. On the mattress sites it recovers only {r_lo * 100:.0f}–{r_hi * 100:.0f}% of their "
         "traffic: the panel under-covers that audience."),
        ("Mattress anchor: Saatva + Nectar + DreamCloud", P_BLUE,
         f"{num(sc['mattress_us_visits_per_day']) / 1e3:.0f}K US visits a day ÷ "
         f"{num(sc['mattress_us_visits_panel']):.0f} panel visits  →  "
         f"**F_mattress = {num(sc['scale_factor_mattress']):,.0f}**",
         f"Used for the four mattress brands. Checked one brand at a time, it reproduces "
         f"{m_lo:.2f}–{m_hi:.2f}× each site's traffic."),
    ]
    for i, (head, color, formula, note) in enumerate(anchors):
        y = 2.62 + i * 1.62
        box(s, L, y, 6.1, 1.48, fill=PANEL)
        box(s, L, y, 0.06, 1.48, fill=color)
        text(s, L + 0.25, y + 0.14, 5.7, 0.3, head, size=12.5, color=NAVY, bold=True)
        text(s, L + 0.25, y + 0.5, 5.7, 0.3, formula, size=11.5, color=INK, accent=NAVY)
        text(s, L + 0.25, y + 0.88, 5.7, 0.55, note, size=10.5, color=MUTED, spacing=1.05)
    text(s, L, 5.95, 6.1, 0.95,
         f"Conservative estimate: F_retail for the mattress brands, and for Walmart the population ratio "
         f"(324M US internet users ÷ {num(sc['us_panel_users']) / 1e3:.0f}K US panel users = "
         f"{num(sc['scale_factor_population']):.0f}). Caveat: Similarweb's latest public month is August, the "
         "Labor Day sale season, so F_mattress may overstate an ordinary May day.",
         size=9.5, color=MUTED, spacing=1.08)

    # Chart: scaled panel visits ÷ Similarweb visits, per brand and factor
    cx = 7.15
    text(s, cx, TOP, R - cx, 0.3, "Scaled panel visits ÷ Similarweb visits", size=12.5, color=NAVY, bold=True)
    for i, (lab, color) in enumerate((("F_retail (walmart.com)", GREY_BAR), ("F_mattress (pooled)", P_BLUE))):
        lx = cx + i * 2.3
        box(s, lx, TOP + 0.47, 0.16, 0.16, fill=color)
        text(s, lx + 0.24, TOP + 0.42, 2.0, 0.25, lab, size=10, color=MUTED)
    px0, px1, vmax = cx + 1.35, R - 0.35, 1.4
    scale = (px1 - px0) / vmax
    y0 = 2.75
    for i, b in enumerate(mattress):
        gy = y0 + i * 1.05
        client = b == "Saatva"
        text(s, cx, gy + 0.12, 1.25, 0.3, b, size=12, bold=client, color=BRONZE_TEXT if client else INK)
        for j, (col, color) in enumerate((("ratio_with_f_retail", GREY_BAR), ("ratio_with_f_mattress", P_BLUE))):
            val = num(v[b][col])
            by = gy + j * 0.36
            box(s, px0, by, val * scale, 0.3, fill=color)
            text(s, px0, by + 0.04, val * scale - 0.08, 0.25, f"{val:.2f}×", size=10,
                 color=WHITE if j == 1 else INK, bold=j == 1, align="r")
    axis_y = y0 + 3 * 1.05 - 0.15
    line(s, px0, y0 - 0.12, px0, axis_y, GRID, 0.75)
    ref = px0 + 1.0 * scale
    line(s, ref, y0 - 0.12, ref, axis_y, NAVY, 1.25, dash=True)
    text(s, ref - 0.9, axis_y + 0.06, 1.8, 0.25, "1.0 = Similarweb", size=9.5, color=NAVY, bold=True, align="c")
    text(s, cx, axis_y + 0.5, R - cx, 0.5,
         "Walmart is 1.00× with F_retail by construction. Helix has no public visit figure, so it is "
         "scaled with F_mattress without its own check.",
         size=9.5, color=MUTED, spacing=1.05)


def slide_results(prs, d):
    s = content_slide(prs, 6, "Results: clicks and conversions",
                      "Saatva: ~16.7K US affiliate clicks a day. One day can't rank the mattress brands.",
                      "Saatva's estimate is about 16.7K US affiliate clicks a day, with a 95% interval of 6.1K to "
                      "36.4K. The mattress intervals overlap, so one day can't rank the brands by volume. No mattress "
                      "order, registration or financing application followed an affiliate click within the day, "
                      "which is expected for a considered purchase, so the conversion range uses a 0.5–2% "
                      "category benchmark. Walmart's volume is large enough to measure: 1.74% of its affiliate "
                      "clicks led to an order.")
    c = d["comp"]
    order = ["Saatva", "Nectar", "Helix", "DreamCloud", "Walmart"]
    rows = [["Brand", "Network", "Panel visits", "Visits from affiliate", "Panel affiliate clicks",
             "Est. US affiliate clicks / day", "95% CI", "Conservative est.", "Est. US converting clicks / day"]]
    for b in order:
        r = c[b]
        clicks = f"{num(r['panel_affiliate_clicks']):,.0f}" + (" ¹" if b == "Saatva" else "")
        if b == "Walmart":
            conv = f"{k(r['est_us_converted_clicks'])}  ({pct(r['pct_clicks_converting'], 2)} of clicks)"
        else:
            conv = f"{k(r['est_us_converted_clicks_benchmark_lo'])}–{k(r['est_us_converted_clicks_benchmark_hi'])} ²"
        rows.append([b, "Impact" if b == "Walmart" else r["networks"], f"{num(r['panel_visits']):,.0f}",
                     pct(r["pct_visits_from_affiliate"]), clicks, k(r["est_us_affiliate_clicks"]),
                     f"{k(r['est_us_affiliate_clicks_lo95'])}–{k(r['est_us_affiliate_clicks_hi95'])}",
                     k(r["est_us_affiliate_clicks_alt"]), conv])
    widths = [1.3, 1.1, 1.0, 1.15, 1.15, 1.5, 1.45, 1.3, 2.18]
    table(s, L, TOP - 0.05, widths, rows, [0.52] + [0.35] * 5, size=11, header_size=10,
          aligns=["l", "l", "r", "r", "r", "r", "r", "r", "r"], bold_cols=(0, 5),
          fills=[None, BRONZE_TINT, None, None, None, None],
          colors=[None, BRONZE_TEXT, None, None, None, None])
    text(s, L, 4.13, CW, 0.45,
         "¹ Five landings plus one Partnerize click that never loaded the site.   ² No mattress order, registration "
         "or financing application followed an affiliate click that day; the range applies a 0.5–2% category "
         "conversion rate.   Conservative: F_retail for the mattress brands, the population ratio for Walmart.   "
         "95% CI: Poisson sampling error of the panel count only.",
         size=8.5, color=MUTED, spacing=1.08)

    # Interval chart for the mattress brands
    gx, gy, gw = L, 4.68, 6.55
    text(s, gx, gy, gw, 0.28, "Est. US affiliate clicks a day, with 95% CI", size=11.5, color=NAVY, bold=True)
    px0, px1, vmax = gx + 1.3, gx + gw - 0.2, 40000
    sc = (px1 - px0) / vmax
    pitch, y1 = 0.36, gy + 0.6
    for i, b in enumerate(order[:4]):
        r = c[b]
        cy = y1 + i * pitch
        client = b == "Saatva"
        color = S_BRONZE if client else GREY_BAR
        lo, hi, est = (num(r["est_us_affiliate_clicks_lo95"]), num(r["est_us_affiliate_clicks_hi95"]),
                       num(r["est_us_affiliate_clicks"]))
        text(s, gx, cy - 0.12, 1.2, 0.25, b, size=10.5, bold=client, color=BRONZE_TEXT if client else INK)
        box(s, px0 + lo * sc, cy - 0.04, (hi - lo) * sc, 0.08, fill=color)
        box(s, px0 + est * sc - 0.08, cy - 0.08, 0.16, 0.16, fill=BRONZE_TEXT if client else MUTED,
            shape=MSO_SHAPE.OVAL, line=WHITE, line_w=1.25)
        text(s, px0 + est * sc + 0.12, cy - 0.27, 0.7, 0.2, k(est), size=8.5, color=INK, bold=client)
    ay = y1 + 4 * pitch - 0.12
    line(s, px0, ay, px1, ay, GRID, 0.75)
    for t in range(0, vmax + 1, 10000):
        text(s, px0 + t * sc - 0.3, ay + 0.04, 0.6, 0.2, f"{t // 1000}K" if t else "0", size=8.5,
             color=MUTED, align="c")

    sa = c["Saatva"]
    notes = [
        ("**Consistent with Similarweb.** Affiliate is 23.7% of saatva.com's traffic, about 16K US visits a "
         "day. The scale is partly calibrated on the same source, so this is a consistency check, not proof."),
        ("**The intervals overlap.** Saatva, Nectar, Helix and DreamCloud can't be ranked on one day's clicks. "
         "The share of visits from affiliates is the robust comparison (next slide)."),
    ]
    nx = 7.55
    for i, body in enumerate(notes):
        y = 4.68 + i * 0.98
        box(s, nx, y, R - nx, 0.86, fill=BLUE_TINT if i == 0 else PANEL)
        text(s, nx + 0.18, y + 0.1, R - nx - 0.36, 0.7, body, size=10.5, color=INK, accent=NAVY, spacing=1.08)


def slide_mix(prs, d):
    s = content_slide(prs, 7, "Results: traffic mix",
                      "Affiliate brings 16% of Saatva's visits, 1.5–4× the share at its mattress rivals",
                      "The share of visits that start with an affiliate click is the more robust comparison: 16% "
                      "for Saatva against 3.9–10.5% for the other mattress brands. Nectar and DreamCloud lean on "
                      "paid search, which Similarweb confirms independently.")
    groups = [("Affiliate", P_BLUE, WHITE, ["Affiliate"]),
              ("Paid search", PAID, WHITE, ["Paid search"]),
              ("Other campaigns (email, social, display/TV)", OTHER, INK,
               ["Email / SMS", "Social (paid/organic)", "Display / TV", "Other tagged"]),
              ("Untagged: organic, direct, referral", UNTAGGED, INK, ["Untagged (organic / direct / referral)"])]
    lx = L
    for lab, color, _, _ in groups:
        box(s, lx, TOP + 0.05, 0.16, 0.16, fill=color)
        text(s, lx + 0.23, TOP, 3.6, 0.25, lab, size=10, color=MUTED)
        lx += 0.4 + len(lab) * 0.068
    brands = ["Saatva", "Helix", "DreamCloud", "Nectar", "Walmart"]
    bx0, bx1 = L + 1.45, 7.85
    bw = bx1 - bx0
    y = TOP + 0.6
    for i, b in enumerate(brands):
        mix = d["mix"][b]
        total = sum(mix.values())
        by = y + i * 0.82 + (0.2 if b == "Walmart" else 0)
        client = b == "Saatva"
        if client:
            box(s, L - 0.18, by, 0.07, 0.5, fill=S_BRONZE)
        text(s, L, by + 0.02, 1.4, 0.26, b, size=12.5, bold=True, color=BRONZE_TEXT if client else INK)
        text(s, L, by + 0.27, 1.4, 0.22, f"{total:,} visits", size=9, color=MUTED)
        x = bx0
        for lab, color, tcolor, keys in groups:
            share = sum(mix.get(key, 0) for key in keys) / total
            seg = share * bw
            if seg <= 0:
                continue
            box(s, x, by, seg, 0.5, fill=color, line=WHITE, line_w=0.75)
            if seg >= 0.5:
                text(s, x, by + 0.13, seg, 0.25, f"{share * 100:.0f}%", size=10, color=tcolor,
                     bold=lab == "Affiliate", align="c")
            x += seg
        aff = mix.get("Affiliate", 0) / total * 100
        text(s, bx1 + 0.15, by + 0.1, 0.9, 0.3, f"{aff:.1f}%", size=14, color=P_DEEP, bold=True)
    text(s, bx1 + 0.15, y - 0.32, 1.0, 0.25, "Affiliate", size=9.5, color=MUTED, bold=True)
    line(s, L, y + 4 * 0.82 + 0.03, bx1 + 1.0, y + 4 * 0.82 + 0.03, GRID, 0.5, dash=True)
    text(s, L, y + 4 * 0.82 + 0.75, 8.2, 0.25,
         "Share of US panel visits by the entry page's traffic source, 1 May 2026. Walmart is the retail benchmark.",
         size=9, color=MUTED)

    px = 9.35
    pw = R - px
    box(s, px, TOP, pw, 3.0, fill=PANEL)
    text(s, px + 0.22, TOP + 0.16, pw - 0.4, 0.5, "Similarweb agrees: top traffic channel (Aug 2026)",
         size=12, color=NAVY, bold=True, spacing=1.0)
    sw = [("Saatva", "Affiliate", "23.7%"), ("Helix", "Affiliate", "21.0%"),
          ("Nectar", "Paid search", ""), ("DreamCloud", "Paid search", "")]
    for i, (b, ch, share) in enumerate(sw):
        ry = TOP + 0.8 + i * 0.5
        client = b == "Saatva"
        text(s, px + 0.22, ry, 1.2, 0.3, b, size=11.5, bold=True, color=BRONZE_TEXT if client else INK)
        aff = ch == "Affiliate"
        pill(s, px + 1.42, ry - 0.01, 1.15, ch, BLUE_TINT if aff else PANEL, P_DEEP if aff else PAID)
        if not aff:
            box(s, px + 1.42, ry - 0.01, 1.15, 0.26, line=OTHER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
        text(s, px + 2.62, ry, 0.56, 0.3, share, size=11.5, color=INK, align="r")
    label_box(s, px, 5.05, pw, 1.55,
              "Affiliate is Saatva's competitive edge, so it is also where hijacked commissions cost "
              "Saatva the most.", NAVY, size=12.5, color=WHITE, margin=0.22, spacing=1.12)


def slide_publishers(prs, d):
    s = content_slide(prs, 8, "Results: publishers",
                      "Rivals reach shoppers through review and HSA/FSA partners not seen in Saatva's traffic",
                      "These are examples, not statistics: one day of panel data. Saatva's six clicks come from "
                      "four publishers. Competitors get traffic from a review site, a buyer's guide and an HSA/FSA "
                      "payment partner that don't appear in Saatva's traffic. Publisher names are inferred from the "
                      "tracking ids, hence 'likely'.")
    lw = 6.25
    label_box(s, L, TOP, lw, 0.46, "Saatva: 6 affiliate clicks from 4 publishers (Partnerize)", S_BRONZE,
              size=12, color=WHITE, bold=True, margin=0.18)
    pubs = [
        ("mattressnrd", "Likely Mattress Nerd, a review site", "3", "Content", BLUE_TINT, P_DEEP),
        ("trafficpoint12345", "TrafficPoint: paid-search listicle, 6 brands in a minute", "1", "Review",
         PANEL, PAID),
        ("brandxemail", "Listed as email; the click came from a Google ad", "1", "Policy check",
         ORANGE_TINT, ORANGE_TEXT),
        ("camref:1011laqH9", "Unknown; fired by a \"new tab\" browser extension", "1", "Cookie stuffing",
         P_ORANGE, WHITE),
    ]
    text(s, L + 0.18, TOP + 0.6, 2.0, 0.22, "Publisher id", size=9, color=MUTED, bold=True)
    text(s, L + 4.25, TOP + 0.6, 0.5, 0.22, "Clicks", size=9, color=MUTED, bold=True, align="c")
    for i, (pid, desc, n, tag, tfill, tcolor) in enumerate(pubs):
        y = TOP + 0.9 + i * 0.72
        text(s, L + 0.18, y, 4.0, 0.25, pid, size=11.5, color=INK, bold=True)
        text(s, L + 0.18, y + 0.27, 4.0, 0.25, desc, size=10, color=MUTED)
        text(s, L + 4.25, y + 0.1, 0.5, 0.3, n, size=14, color=INK, bold=True, align="c")
        pill(s, L + 4.85, y + 0.1, 1.25, tag, tfill, tcolor)
        line(s, L + 0.18, y + 0.62, L + lw - 0.15, y + 0.62, GRID, 0.5)

    rx = L + lw + 0.35
    rw = R - rx
    label_box(s, rx, TOP, rw, 0.46, "Rivals' partners not seen in Saatva's traffic", NAVY,
              size=12, color=WHITE, bold=True, margin=0.18)
    rivals = [
        ("Helix", "mattressclarity.com", "Review site"),
        ("DreamCloud", "WickFire (likely), via buyersguide.org", "Comparison / buyer's guide"),
        ("Nectar", "Truemed", "HSA/FSA payment: pay with pre-tax health funds"),
    ]
    text(s, rx + 0.18, TOP + 0.6, 1.5, 0.22, "Brand", size=9, color=MUTED, bold=True)
    text(s, rx + 1.5, TOP + 0.6, 3.5, 0.22, "Partner sending the click", size=9, color=MUTED, bold=True)
    for i, (b, partner, kind) in enumerate(rivals):
        y = TOP + 0.9 + i * 0.72
        text(s, rx + 0.18, y + 0.1, 1.3, 0.3, b, size=11.5, color=INK, bold=True)
        text(s, rx + 1.5, y, rw - 1.65, 0.25, partner, size=11.5, color=INK, bold=True)
        text(s, rx + 1.5, y + 0.27, rw - 1.65, 0.25, kind, size=10, color=MUTED)
        line(s, rx + 0.18, y + 0.62, R - 0.15, y + 0.62, GRID, 0.5)
    text(s, rx + 0.18, TOP + 3.1, rw - 0.3, 0.5,
         "Partner = the site the user was on just before the click.",
         size=9.5, color=MUTED, italic=True)

    box(s, L, 5.88, CW, 0.82, fill=BRONZE_TINT)
    box(s, L, 5.88, 0.07, 0.82, fill=S_BRONZE)
    text(s, L + 0.25, 5.98, CW - 0.45, 0.65,
         "**Coupons:** every Saatva affiliate landing auto-applied a coupon, and Mattress Nerd and TrafficPoint used "
         "the same code. A shared code can't identify the publisher, and a leaked code earns commission anywhere.",
         size=11, color=INK, accent=BRONZE_TEXT, spacing=1.1)


def slide_growth(prs, d):
    s = content_slide(prs, 9, "Recommendations: growth",
                      "Grow where competitors already win, and pay for the assist, not the last touch",
                      "Five actions, each tied to evidence in the data. The principle behind 3 and 4: pay for the "
                      "click that created the sale, not for the one that touched it last.")
    s30 = d["sens"][("Walmart", "30 min (base)")]
    recs = [
        ("Recruit review, comparison and HSA/FSA partners",
         "Start with partners rivals already use: review sites (Mattress Clarity), buyer's guides "
         "(buyersguide.org) and HSA/FSA payment (Truemed).",
         "Each sent shoppers to Helix, DreamCloud or Nectar; none appeared in Saatva's traffic."),
        ("Give every publisher its own coupon code",
         "Unique codes show which partner drove the sale, and stop leaked codes from earning commission elsewhere.",
         "Mattress Nerd and TrafficPoint landings auto-applied the same code."),
        ("Tier commissions by the value of the click",
         "Pay more for content and new customers; pay less for coupon and cash-back clicks, and for clicks "
         "after a cart exists.",
         f"At Walmart, clicks after the cart convert at {num(s30['cr_checkout_pct']):.0f}% vs 0.4%: "
         "they close sales already under way."),
        ("Set a PPC policy and de-duplicate against paid search",
         "Ban affiliate bidding on Saatva's brand terms, or allow it at a lower rate. Don't pay an affiliate "
         "and Google for the same order.",
         "brandxemail's click came from a Google ad; a TrafficPoint user returned through a Shopping ad."),
        ("Judge publishers on 30-day journeys and incrementality",
         "Mattresses are a considered purchase: measure 30-day conversion per publisher, and run holdout tests.",
         "No mattress order followed an affiliate click within the same day."),
    ]
    pitch = 0.98
    for i, (head, body, ev) in enumerate(recs):
        y = TOP + i * pitch
        label_box(s, L, y + 0.06, 0.46, 0.46, str(i + 1), S_BRONZE, shape=MSO_SHAPE.OVAL, size=14,
                  color=WHITE, bold=True, align="c", margin=0)
        text(s, L + 0.7, y + 0.02, 6.3, 0.3, head, size=13, color=NAVY, bold=True)
        text(s, L + 0.7, y + 0.34, 6.3, 0.55, body, size=10.5, color=INK, spacing=1.06)
        box(s, 7.75, y + 0.02, R - 7.75, pitch - 0.14, fill=PANEL)
        text(s, 7.92, y + 0.1, R - 7.92 - 0.15, pitch - 0.28, [("EVIDENCE", {"size": 8, "bold": True,
             "color": MUTED, "spc": 100, "after": 2}), ev], size=10, color=INK, spacing=1.05)
        if i < len(recs) - 1:
            line(s, L + 0.7, y + pitch - 0.06, 7.55, y + pitch - 0.06, GRID, 0.5)


def slide_hijack_evidence(prs, d):
    s = content_slide(prs, 10, "Attribution hijacking: evidence",
                      "At Walmart, the 13–23% of flagged clicks take 52–79% of affiliate-credited orders",
                      "Walmart has the volume to test the indicators. Clicks fired after the shopper was already in "
                      "the cart convert at 13%, against 0.4% for clicks with no indicator, and the order follows a "
                      "median 2.3 minutes later: these clicks close sales that were already happening. The result "
                      "holds when the look-back shrinks from 30 to 2 minutes.")
    sig = {r["primary_signal"][2:]: r for r in d["signal"]}
    rows = [("Injected at cart / checkout", "Injected at cart/checkout"),
            ("Already on the brand's site", "User already on brand site"),
            ("Coupon / cash-back just before", "Coupon/cash-back just before"),
            ("No visible referrer", "No visible referrer (weak)"),
            ("No indicator", "No hijack indicator")]
    total = sum(int(r["clicks"]) for r in d["signal"])
    text(s, L, TOP, 7.0, 0.3, f"Walmart, {total:,} affiliate clicks: share of clicks vs share of credited orders",
         size=12, color=NAVY, bold=True)
    for i, (lab, color) in enumerate((("Share of clicks", GREY_BAR), ("Share of credited orders", P_ORANGE))):
        lx = L + i * 2.0
        box(s, lx, TOP + 0.45, 0.16, 0.16, fill=color)
        text(s, lx + 0.23, TOP + 0.4, 1.8, 0.25, lab, size=10, color=MUTED)
    text(s, 6.75, TOP + 0.4, 0.9, 0.25, "Conv. rate", size=10, color=MUTED, bold=True, align="r")
    bx0, bx1, vmax = L + 2.45, 6.05, 80.0
    sc = (bx1 - bx0) / vmax
    y0, pitch = TOP + 0.85, 0.7
    for i, (lab, key) in enumerate(rows):
        r = sig[key]
        y = y0 + i * pitch
        clean = key == "No hijack indicator"
        if clean:
            line(s, L, y - 0.1, 7.65, y - 0.1, GRID, 0.5, dash=True)
        text(s, L, y + 0.08, 2.35, 0.3, lab, size=10.5, color=INK, bold=not clean)
        for j, (col, color) in enumerate((("pct_of_clicks", GREY_BAR),
                                          ("pct_of_converted_clicks", P_BLUE if clean else P_ORANGE))):
            v = num(r[col])
            by = y + j * 0.25
            box(s, bx0, by, max(v * sc, 0.02), 0.21, fill=color)
            text(s, bx0 + v * sc + 0.07, by - 0.01, 0.7, 0.22, f"{v:.1f}%", size=9.5, color=INK, bold=j == 1)
        text(s, 6.75, y + 0.08, 0.9, 0.3, pct(r["cr_pct"]), size=12, color=ORANGE_TEXT if not clean else P_DEEP,
             bold=True, align="r")
    text(s, L, y0 + 5 * pitch + 0.02, 7.05, 0.45,
         "Each click counts once, under its first signal (30-minute look-back). Not shown: publisher-bought search "
         "ads (0.4% of clicks) and multi-brand bursts (0.1%), with no orders.",
         size=8.5, color=MUTED, spacing=1.05)

    rx = 8.05
    rw = R - rx
    card_header(s, rx, TOP, rw, "Robust to the look-back window", P_ORANGE, size=12.5)
    srows = [["Look-back", "Clicks flagged", "Orders from flagged", "Conv. rate: flagged vs other"]]
    for lb, name in (("30 min (base)", "30 min"), ("10 min", "10 min"), ("2 min", "2 min")):
        r = d["sens"][("Walmart", lb)]
        srows.append([name, pct(r["pct_clicks_strong"]), pct(r["pct_orders_from_strong"]),
                      f"{pct(r['cr_strong_pct'])} vs {pct(r['cr_other_pct'])}"])
    table(s, rx, TOP + 0.42, [0.95, 1.05, 1.15, 1.53], srows, [0.5, 0.36, 0.36, 0.36], size=10.5,
          header_size=9, aligns=["l", "r", "r", "r"], bold_cols=(0, 2))

    redirect = next(r for r in d["sources"] if r["primary_signal"].startswith("1") and r["prev_host"] == "walmart.com")
    bizrate = sum(int(r["clicks"]) for r in d["sources"]
                  if r["prev_host"] == "rd.bizrate.com" and r["primary_signal"][0] in "0123")
    s30 = d["sens"][("Walmart", "30 min (base)")]
    card_header(s, rx, 4.0, rw, "How the commission is taken", P_ORANGE, size=12.5)
    text(s, rx + 0.17, 4.42, rw - 0.17, 2.5, [
        f"**Silent redirect from walmart.com itself:** {int(redirect['clicks'])} cart-stage clicks fired a median "
        f"{num(redirect['median_secs_since_prev']):.0f} s after a walmart.com page, with no publisher page between.",
        f"**Price-comparison redirects mid-session:** rd.bizrate.com, {bizrate} flagged clicks.",
        "**Coupon and cash-back extensions:** Capital One Shopping, Slickdeals, Rakuten.",
        f"Clicks injected at the cart lead to an order a median **{num(s30['median_min_to_order_checkout']):.1f} "
        "minutes** later.",
    ], size=10.5, color=INK, bullet=True, after=5, spacing=1.06)


def journey(s, x, y, w, steps, final_fill, final_color, final_line=None):
    """Vertical chain of steps; the last one highlighted."""
    h, gap = 0.38, 0.2
    for i, st in enumerate(steps):
        yy = y + i * (h + gap)
        last = i == len(steps) - 1
        label_box(s, x, yy, w, h, st, final_fill if last else WHITE, size=10, color=final_color if last else INK,
                  bold=last, align="c", margin=0.06, line=final_line if last else GRID,
                  shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.2)
        if not last:
            line(s, x + w / 2, yy + h + 0.02, x + w / 2, yy + h + gap - 0.02, MUTED, 1.0, arrow=True)
    return y + len(steps) * (h + gap) - gap


def slide_saatva_cases(prs, d):
    s = content_slide(prs, 11, "Attribution hijacking: Saatva",
                      "The same patterns already appear in Saatva's own program",
                      "Three cases from Saatva's own clicks. The first is direct evidence of cookie stuffing: the "
                      "network registered a click, but the site never loaded. The second is a policy question. The "
                      "third looked like stuffing, but the user's later behaviour cleared it. That is why the "
                      "indicators should trigger a review, not an automatic penalty.")
    cases = [
        ("COOKIE STUFFING", P_ORANGE, WHITE, "A browser extension fires a Partnerize click",
         ["newtab.club  (\"new tab\" extension)", "tatrck.com/clickGate", "saatva.prf.hn click · camref:1011laqH9",
          "×  saatva.com never loads"], ORANGE_TINT, ORANGE_TEXT, P_ORANGE,
         "At that moment the user was browsing Sleep Number. If they buy from Saatva within the cookie window, "
         "the extension takes the commission.",
         "Reconcile Partnerize clicks with saatva.com landings; reverse and block the source."),
        ("UNDECLARED PAID SEARCH", ORANGE_TINT, ORANGE_TEXT, "An \"email\" publisher's click comes from a Google ad",
         ["Google ad  (gad_source=1)", "brandxemail affiliate click", "saatva.com/sale + auto-applied coupon"],
         ORANGE_TINT, ORANGE_TEXT, None,
         "The declared method is email, but the traffic came from paid search, where it may compete with "
         "Saatva's own brand ads.",
         "Check it against the PPC and trademark terms; require declared traffic sources."),
        ("REVIEW BEFORE ACTING", BLUE_TINT, P_DEEP, "A paid-search listicle sends one user to 6 brands",
         ["Search ad", "TrafficPoint listicle", "6 brands, 7 landings in about a minute"],
         BLUE_TINT, P_DEEP, None,
         "The user then browsed the sites, so this is not stuffing. But 9 minutes later they came back through a "
         "Google Shopping ad, likely Saatva's own: Saatva may pay twice.",
         "De-duplicate affiliate and paid-search credit before paying."),
    ]
    cw, gap = (CW - 0.5) / 3, 0.25
    for i, (tag, tfill, tcolor, title, steps, ffill, fcolor, fline, detail, action) in enumerate(cases):
        x = L + i * (cw + gap)
        box(s, x, TOP, cw, 4.98, fill=PANEL)
        label_box(s, x, TOP, cw, 0.4, tag, tfill, size=10, color=tcolor, bold=True, margin=0.18, spc=120)
        text(s, x + 0.2, TOP + 0.55, cw - 0.4, 0.55, title, size=13, color=NAVY, bold=True, spacing=1.02)
        end = journey(s, x + 0.25, TOP + 1.22, cw - 0.5, steps, ffill, fcolor, fline)
        ty = max(end + 0.16, TOP + 3.5)
        text(s, x + 0.2, ty, cw - 0.4, 0.9, detail, size=10.5, color=INK, spacing=1.08)
        text(s, x + 0.2, TOP + 4.42, cw - 0.4, 0.5, f"**Action:** {action}", size=10.5, color=INK,
             accent=NAVY, spacing=1.06)


def slide_fraud_controls(prs, d):
    s = content_slide(prs, 12, "Recommendations: fraud controls",
                      "Detect hijacking per publisher, then change the rules that make it pay",
                      "Detection per publisher first, then rules that remove the incentive. The cheapest and most "
                      "decisive control is to reconcile Partnerize click logs with landings on saatva.com: a click "
                      "that never lands needs no threshold to tune.")
    s30 = d["sens"][("Walmart", "30 min (base)")]
    sig = {r["primary_signal"][2:]: r for r in d["signal"]}
    inj = sig["Injected at cart/checkout"]
    card_header(s, L, TOP, 7.3, "Monitor weekly, per publisher", P_ORANGE, size=13)
    rows = [
        ["Indicator", "Flag when", "Seen in this data"],
        ["Click without landing", "A Partnerize click has no saatva.com landing", "\"New tab\" extension (Saatva)"],
        ["Click while already on site or in cart", "A publisher's share is far above the program's",
         f"Walmart: {pct(inj['pct_of_clicks'])} of clicks, {pct(inj['pct_of_converted_clicks'])} of orders"],
        ["Fast click-to-order", "Median under 5 minutes",
         f"Walmart: {num(s30['median_min_to_order_checkout']):.1f} min after cart-stage clicks"],
        ["Ad click ids on affiliate landings", "gclid or gad_source on the landing URL", "brandxemail (Saatva)"],
        ["Declared vs actual source", "The promotion method doesn't match the referrers",
         "brandxemail: \"email\", via a Google ad"],
        ["Multi-brand bursts", "3+ advertisers in 2 minutes with no engagement", "TrafficPoint: cleared on review"],
    ]
    table(s, L, TOP + 0.45, [2.3, 2.55, 2.45], rows, [0.4] + [0.56] * 6, size=10, header_size=9.5)
    rx = 8.3
    rw = R - rx
    card_header(s, rx, TOP, rw, "Change the program rules", NAVY, size=13)
    rules = [
        "**No overwrite after cart creation:** a click after the cart exists doesn't take the commission, or "
        "earns a reduced rate.",
        "**Extension stand-down:** extensions may not fire when the user arrived from another partner or is "
        "already on the site.",
        "**PPC and trademark policy,** with monitoring of brand-term ads.",
        "**Payout hold** of 30–45 days, with reversals for flagged orders.",
        "**Validate and tune:** test the indicators against confirmed fraud and reversals, and run holdout tests.",
    ]
    for i, r in enumerate(rules):
        y = TOP + 0.47 + i * 0.75
        label_box(s, rx, y + 0.02, 0.32, 0.32, str(i + 1), NAVY, shape=MSO_SHAPE.OVAL, size=10.5, color=WHITE,
                  bold=True, align="c", margin=0)
        text(s, rx + 0.45, y, rw - 0.45, 0.72, r, size=10.5, color=INK, accent=NAVY, spacing=1.06)
    label_box(s, L, 6.15, CW, 0.62,
              "**Start here:** reconcile Partnerize click logs with saatva.com landings. A click id that never lands "
              "is direct evidence, with no threshold to tune.", NAVY, size=12, color=WHITE, accent=P_ORANGE,
              margin=0.25)


def slide_limitations(prs, d):
    s = content_slide(prs, 13, "Limitations and next steps",
                      "One panel day sets the direction; 90 days and Saatva's own logs would size it",
                      "One panel day sets direction, not size. The same pipeline can run on 30–90 days of panel data "
                      "and on Saatva's own Partnerize click and order logs, which cover every click.")
    rows = [
        ["Limitation", "What it means", "Next step"],
        ["One day of panel data", "2–6 affiliate clicks per mattress brand, and no completed orders",
         "Run the same pipeline on 30–90 days, and on Saatva's Partnerize click and order logs, which cover every "
         "click rather than a sample"],
        ["Scaling relies on public estimates for another month",
         "F may be off; August is the Labor Day sale season",
         "Calibrate on same-period figures (paid Similarweb, Partnerize benchmarks), split by device"],
        ["Same-day conversion window", "Misses orders placed days after the click; affiliate cookies typically "
         "last 30 days", "Follow multi-day user journeys"],
        ["Hijack indicators are behavioural proxies", "The strongest evidence comes from Walmart's volume",
         "Validate against confirmed fraud and reversals; holdout tests for incrementality"],
        ["Saatva's cart doesn't change the URL", "No cart or checkout steps are visible for Saatva, so no funnel "
         "comparison", "Use Saatva's on-site events: add to cart, checkout start"],
    ]
    table(s, L, TOP, [3.1, 4.15, 4.88], rows, [0.42] + [0.72] * 5, size=11, header_size=10)
    text(s, L, 6.25, CW, 0.5, f"Code, SQL and result tables: **{REPO}**", size=12, color=INK, accent=P_DEEP)


def appendix_pipeline(prs, d):
    s = content_slide(prs, 14, "Appendix", "A1 · The pipeline: ten SQL steps, run in order",
                      "Each SQL file documents its own logic at the top. The runner prints row counts after each "
                      "step as a sanity check.")
    rows = [["Step", "File", "What it does"]] + [[f"{i:02d}", f, w] for i, (f, w) in enumerate([
        ("01_raw_view.sql", "View over the Parquet files"),
        ("02_data_quality.sql", "Validation profile: rows, ids, duplicates, nulls, hourly profile"),
        ("03_brand_user_events.sql", "Working dataset: brand users' events, deduplicated, mirror IDs merged"),
        ("04_affiliate_clicks.sql", "Tagged landings + redirect hops → deduplicated clicks, network, publisher"),
        ("05_brand_visits.sql", "Visits (30-minute rule) and their entry traffic source"),
        ("06_conversions.sql", "Orders, registrations, financing, funnel steps; last-click attribution"),
        ("07_hijacking_signals.sql", "Hijacking indicators per affiliate click"),
        ("08_us_scaling.sql", "US users, external benchmarks, scale factors and their validation"),
        ("09_summary.sql", "Result tables"),
        ("10_sensitivity.sql", "Hijacking indicators under stricter look-back windows"),
    ], start=1)]
    table(s, L, TOP, [0.8, 3.0, 8.33], rows, [0.4] + [0.4] * 10, size=11, header_size=10, bold_cols=(1,))
    text(s, L, 6.35, CW, 0.5,
         f"Runner: scripts/run_pipeline.py (row-count checks, CSV exports to outputs/). About 30 seconds on 48.4M "
         f"rows with DuckDB.  **{REPO}**", size=10.5, color=MUTED, accent=P_DEEP)


def appendix_indicators(prs, d):
    s = content_slide(prs, 15, "Appendix", "A2 · Attribution-hijacking indicators, per affiliate click",
                      "Tiers: strong indicators are the ones a publisher would struggle to explain; medium ones are "
                      "legitimate for some partner types; review ones need a person to look at the journey.")
    rows = [
        ["Indicator", "Definition", "Tier"],
        ["Click without landing", "The network registered a click, but the brand's site never loaded (cookie stuffing)",
         "Strong"],
        ["Injected at cart / checkout", "The user was in the brand's cart or checkout in the 30 minutes before the click",
         "Strong"],
        ["Already on site", "The user was on the brand's site, without an affiliate tag, in the 30 minutes before",
         "Strong"],
        ["Publisher-bought search ad", "The affiliate landing carries a Google or Bing ad click id (gclid, gad_source)",
         "Strong (policy)"],
        ["Brand search before", "A search for the brand name within 60 seconds before the click", "Medium"],
        ["Coupon / cash-back before", "A coupon or cash-back site or extension fired within 60 seconds before",
         "Medium"],
        ["Multi-brand burst", "Landings on 2+ other advertisers within ±2 minutes; stuffing only if the user never "
         "engages", "Review"],
        ["No visible referrer", "No activity in the 30 minutes before (also true for app and email clicks)", "Weak"],
    ]
    tier = {"Strong": ORANGE_TINT, "Strong (policy)": ORANGE_TINT}
    table(s, L, TOP, [2.6, 7.73, 1.8], rows, [0.4] + [0.5] * 8, size=11, header_size=10,
          fills=[None] + [tier.get(r[2]) for r in rows[1:]])
    text(s, L, 6.4, CW, 0.4, "The 30-minute look-back is tested at 10 and 2 minutes in 10_sensitivity.sql.",
         size=10.5, color=MUTED)


def appendix_signals(prs, d):
    s = content_slide(prs, 16, "Appendix", "A3 · Walmart: outcomes by primary signal (30-minute look-back)",
                      "Each click is assigned its first-ranked signal, so the rows add up to all clicks.")
    rows = [["Primary signal", "Clicks", "Share of clicks", "Converted clicks", "Conversion rate",
             "Share of credited orders"]]
    for r in d["signal"]:
        rows.append([r["primary_signal"][2:], f"{int(r['clicks']):,}", pct(r["pct_of_clicks"]),
                     f"{int(r['converted_clicks']):,}", pct(r["cr_pct"], 2), pct(r["pct_of_converted_clicks"])])
    fills = [None] + [ORANGE_TINT if r["primary_signal"][0] in "0123" else None for r in d["signal"]]
    table(s, L, TOP, [3.9, 1.4, 1.6, 1.7, 1.6, 1.93], rows, [0.45] + [0.45] * len(d["signal"]), size=11,
          header_size=10, aligns=["l", "r", "r", "r", "r", "r"], fills=fills)
    text(s, L, 6.0, CW, 0.6,
         "Highlighted: strong signals. Converted = the user reached walmart.com's order confirmation after the click "
         "and before any later affiliate click for Walmart, the same day.", size=10.5, color=MUTED, spacing=1.08)


def appendix_sources(prs, d):
    s = content_slide(prs, 17, "Appendix", "A4 · External sources",
                      "All external figures are public pages, retrieved on 4 October 2026.")
    items = [
        ("**Similarweb** website pages for walmart.com, saatva.com, nectarsleep.com, dreamcloudsleep.com and "
         "helixsleep.com, retrieved 4 Oct 2026 (latest month: August 2026): monthly visits, US share, top channels.",
         "similarweb.com/website/saatva.com  (same path for each domain)"),
        ("**DataReportal, Digital 2026:** 324M US internet users (93.1% of the population).",
         "datareportal.com/reports/digital-2026-six-billion-internet-users"),
        ("**Grips Intelligence** retailer pages (us-mattress.com, mattressfirmep.com, mattressfirm.com): mattress "
         "e-commerce conversion rates of 0.5–2%.",
         "gripsintelligence.com/insights/retailers/us-mattress.com"),
    ]
    paras = []
    for body, url in items:
        paras += [(body, {"bullet": True, "after": 2}),
                  (url, {"size": 10.5, "color": P_DEEP, "after": 12, "bullet": False, "margin": 0.17})]
    text(s, L, TOP, CW, 3.6, paras, size=12.5, color=INK, accent=NAVY, spacing=1.12)


# Theme -----------------------------------------------------------------------------
def set_theme(prs):
    """Theme fonts and colours, so text and shapes added later in Google Slides match."""
    part = prs.slide_master.part.part_related_by(RT.THEME)
    root = etree.fromstring(part.blob)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    root.find(".//a:majorFont/a:latin", ns).set("typeface", TITLE_FONT)
    root.find(".//a:minorFont/a:latin", ns).set("typeface", BODY_FONT)
    scheme = root.find(".//a:clrScheme", ns)
    colours = {"dk2": NAVY, "lt2": PANEL, "accent1": P_BLUE, "accent2": P_ORANGE, "accent3": S_BRONZE,
               "accent4": P_DEEP, "accent5": PAID, "accent6": GREY_BAR}
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
    for build in (slide_title, slide_summary, slide_approach, slide_data_quality, slide_scaling, slide_results,
                  slide_mix, slide_publishers, slide_growth, slide_hijack_evidence, slide_saatva_cases,
                  slide_fraud_controls, slide_limitations, appendix_pipeline, appendix_indicators,
                  appendix_signals, appendix_sources):
        build(prs, d)
    register_notes_master(prs)
    prs.save(OUT)
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(prs.slides)} slides")


if __name__ == "__main__":
    main()
