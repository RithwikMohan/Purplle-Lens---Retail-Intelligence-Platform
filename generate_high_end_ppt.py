import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
from pptx.oxml.ns import qn
from lxml import etree

# ── Color Palette ──────────────────────────────────────────────────────────────
BG_DARK      = RGBColor(0x0D, 0x0D, 0x1A)   # near-black navy
BG_CARD      = RGBColor(0x13, 0x13, 0x2B)   # card bg
PURPLE_VIVID = RGBColor(0xA0, 0x55, 0xFF)   # hero accent
PURPLE_MID   = RGBColor(0x7B, 0x2F, 0xBF)
PURPLE_LIGHT = RGBColor(0xD4, 0xA8, 0xFF)
CYAN_ACCENT  = RGBColor(0x00, 0xE5, 0xFF)
WHITE        = RGBColor(0xFF, 0xFF, 0xFF)
GRAY_TEXT    = RGBColor(0xB0, 0xB0, 0xC8)
RED_ACCENT   = RGBColor(0xFF, 0x4A, 0x6B)

SLIDE_W = Inches(16)
SLIDE_H = Inches(9)

IMG_DIR = r"C:\Users\User\.gemini\antigravity-ide\brain\4c44466e-9827-4ef5-aab7-88784a10bf23"
IMG = {
    "dashboard":  os.path.join(IMG_DIR, "media__1780578735779.png"),
    "heatmap":    os.path.join(IMG_DIR, "media__1780578735896.png"),
    "events":     os.path.join(IMG_DIR, "media__1780578735950.png"),
    "camera":     os.path.join(IMG_DIR, "media__1780578735990.png"),
    "anomalies":  os.path.join(IMG_DIR, "media__1780578735996.png"),
}

prs = Presentation()
prs.slide_width  = SLIDE_W
prs.slide_height = SLIDE_H
BLANK = prs.slide_layouts[6]

# ── Helpers ────────────────────────────────────────────────────────────────────

def bg(slide, color=BG_DARK):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color

def rect(slide, left, top, w, h, color, alpha=None):
    shape = slide.shapes.add_shape(1, left, top, w, h)
    shape.line.fill.background()
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    return shape

def txt(slide, text, left, top, w, h, size=24, bold=False,
        color=WHITE, align=PP_ALIGN.LEFT, wrap=True):
    box = slide.shapes.add_textbox(left, top, w, h)
    tf  = box.text_frame
    tf.word_wrap = wrap
    p   = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.color.rgb = color
    return box

def multiline(slide, lines, left, top, w, h, size=22, color=GRAY_TEXT,
              bullet="●", spacing=1.0):
    box = slide.shapes.add_textbox(left, top, w, h)
    tf  = box.text_frame
    tf.word_wrap = True
    first = True
    for line in lines:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        run = p.add_run()
        run.text = f"{bullet}  {line}"
        run.font.size = Pt(size)
        run.font.color.rgb = color

def accent_bar(slide, top, h=Inches(0.06), color=PURPLE_VIVID):
    rect(slide, 0, top, SLIDE_W, h, color)

def add_image(slide, path, left, top, width=None, height=None):
    if os.path.exists(path):
        kw = {}
        if width:  kw["width"]  = width
        if height: kw["height"] = height
        slide.shapes.add_picture(path, left, top, **kw)

def section_header(slide, icon, label, color=PURPLE_VIVID):
    rect(slide, Inches(0.55), Inches(1.35), Inches(0.06), Inches(0.55), color)
    txt(slide, f"{icon}  {label}",
        Inches(0.7), Inches(1.3), Inches(10), Inches(0.65),
        size=14, bold=True, color=color)

def slide_number(slide, n, total=9):
    txt(slide, f"{n} / {total}",
        Inches(14.8), Inches(8.55), Inches(1), Inches(0.4),
        size=11, color=GRAY_TEXT, align=PP_ALIGN.RIGHT)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 1 — TITLE
# ══════════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
bg(sl, RGBColor(0x09, 0x09, 0x18))

# Gradient bar left-edge
rect(sl, 0, 0, Inches(0.35), SLIDE_H, PURPLE_VIVID)

# Soft glow block
rect(sl, Inches(0.35), Inches(2.2), Inches(10), Inches(4.5), BG_CARD)

# Purplle brand mark
txt(sl, "PURPLLE", Inches(0.55), Inches(2.35), Inches(8), Inches(0.7),
    size=13, bold=True, color=PURPLE_LIGHT, align=PP_ALIGN.LEFT)

# Main title
txt(sl, "Store Intelligence\nSystem",
    Inches(0.55), Inches(2.85), Inches(10), Inches(2.2),
    size=64, bold=True, color=WHITE, align=PP_ALIGN.LEFT)

# Tagline
txt(sl, "Real-time retail analytics — from CCTV to actionable insight.",
    Inches(0.55), Inches(5.1), Inches(9.5), Inches(0.7),
    size=22, color=GRAY_TEXT)

# Bottom accent
accent_bar(sl, SLIDE_H - Inches(0.06))

# Dashboard screenshot – right side
add_image(sl, IMG["dashboard"], Inches(10.3), Inches(0.8), width=Inches(5.5))

slide_number(sl, 1)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 2 — THE PROBLEM
# ══════════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
bg(sl)
accent_bar(sl, 0)

txt(sl, "The Problem", Inches(0.6), Inches(0.25), Inches(10), Inches(0.8),
    size=42, bold=True, color=WHITE)

section_header(sl, "🔍", "Physical Retail is Flying Blind")

problems = [
    "Store managers have no live view of how many customers are inside.",
    "No way to know which product zones attract the most dwell time.",
    "Conversion drop-offs are discovered days later via POS reports.",
    "Billing queue spikes cause walk-outs — invisible until it's too late.",
    "Staff can't distinguish visitors from customers without manual counting.",
]

multiline(sl, problems, Inches(0.7), Inches(2.05), Inches(9.5), Inches(5),
          size=23, color=GRAY_TEXT, bullet="⚠")

# Right panel — stat callouts
for i, (val, label, col) in enumerate([
    ("68%",  "avg funnel drop-off\nbetween entry & zone visit", PURPLE_VIVID),
    ("4–5 min", "avg queue tolerance\nbefore abandonment",       RED_ACCENT),
    ("0",    "real-time alerts in\nmost physical stores today",  CYAN_ACCENT),
]):
    x = Inches(11.0)
    y = Inches(1.5 + i * 2.3)
    rect(sl, x, y, Inches(4.5), Inches(1.9), BG_CARD)
    txt(sl, val,   x + Inches(0.2), y + Inches(0.1), Inches(4), Inches(0.9),
        size=48, bold=True, color=col, align=PP_ALIGN.LEFT)
    txt(sl, label, x + Inches(0.2), y + Inches(0.95), Inches(4), Inches(0.9),
        size=15, color=GRAY_TEXT)

accent_bar(sl, SLIDE_H - Inches(0.06))
slide_number(sl, 2)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 3 — OUR SOLUTION
# ══════════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
bg(sl)
accent_bar(sl, 0)

txt(sl, "Our Solution", Inches(0.6), Inches(0.25), Inches(12), Inches(0.8),
    size=42, bold=True, color=WHITE)
section_header(sl, "💡", "End-to-End Store Intelligence Platform")

txt(sl, "We turn existing CCTV footage + POS data into a real-time intelligence layer — "
        "no new hardware required.",
    Inches(0.7), Inches(2.0), Inches(9.5), Inches(0.8),
    size=21, color=GRAY_TEXT)

pillars = [
    ("👁  Detect",   "YOLOv8 Nano tracks every\nperson entering the store.",      PURPLE_VIVID),
    ("🔗  Track",    "Cross-camera Re-ID links\nthe same person across zones.",     PURPLE_MID),
    ("📊  Analyse",  "FastAPI + SQLite compute\nlive metrics & conversions.",       CYAN_ACCENT),
    ("🚨  Alert",    "Anomaly engine fires instant\nalerts for queues & drop-offs.", RED_ACCENT),
]
for i, (title, body, col) in enumerate(pillars):
    x = Inches(0.55 + i * 3.85)
    y = Inches(3.0)
    rect(sl, x, y, Inches(3.6), Inches(3.8), BG_CARD)
    rect(sl, x, y, Inches(3.6), Inches(0.08), col)
    txt(sl, title, x + Inches(0.2), y + Inches(0.22), Inches(3.2), Inches(0.7),
        size=20, bold=True, color=col)
    txt(sl, body,  x + Inches(0.2), y + Inches(0.95), Inches(3.2), Inches(2.6),
        size=18, color=GRAY_TEXT)

accent_bar(sl, SLIDE_H - Inches(0.06))
slide_number(sl, 3)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 4 — ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
bg(sl)
accent_bar(sl, 0)

txt(sl, "How It Works", Inches(0.6), Inches(0.25), Inches(12), Inches(0.8),
    size=42, bold=True, color=WHITE)
section_header(sl, "⚙", "3-Layer Architecture")

steps = [
    ("PIPELINE",    "detect.py  →  tracker.py  →  emit.py",
     "YOLOv8n processes 1 frame/sec\nHSV Re-ID across cameras\nEmits JSONL events", PURPLE_VIVID),
    ("API ENGINE",  "FastAPI  +  SQLite",
     "POST /events/ingest (batch)\nGET /stores/{id}/metrics\nGET /stores/{id}/anomalies", CYAN_ACCENT),
    ("DASHBOARD",   "HTML + CSS + Chart.js",
     "Auto-refresh every 5s\nKPI cards, funnel, heatmap\nAnomaly alerts, event stream", PURPLE_LIGHT),
]
for i, (title, sub, body, col) in enumerate(steps):
    x = Inches(0.55 + i * 5.15)
    y = Inches(2.1)
    rect(sl, x, y, Inches(4.85), Inches(5.5), BG_CARD)
    rect(sl, x, y, Inches(0.08), Inches(5.5), col)
    txt(sl, title, x + Inches(0.25), y + Inches(0.2),  Inches(4.4), Inches(0.6),
        size=22, bold=True, color=col)
    txt(sl, sub,   x + Inches(0.25), y + Inches(0.85), Inches(4.4), Inches(0.6),
        size=14, color=GRAY_TEXT)
    # divider
    rect(sl, x + Inches(0.25), y + Inches(1.5), Inches(4.3), Inches(0.02), PURPLE_MID)
    txt(sl, body,  x + Inches(0.25), y + Inches(1.65), Inches(4.4), Inches(3.5),
        size=17, color=GRAY_TEXT)
    # arrow between boxes (not after last)
    if i < 2:
        txt(sl, "→", x + Inches(5.0), y + Inches(2.4), Inches(0.5), Inches(0.5),
            size=28, bold=True, color=PURPLE_MID)

txt(sl, "POS CSV auto-imported at startup and correlated with billing events via 5-min window",
    Inches(0.55), Inches(7.9), Inches(14), Inches(0.5),
    size=14, color=GRAY_TEXT)

accent_bar(sl, SLIDE_H - Inches(0.06))
slide_number(sl, 4)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 5 — LIVE DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
bg(sl)
accent_bar(sl, 0)

txt(sl, "Live Dashboard", Inches(0.6), Inches(0.25), Inches(12), Inches(0.8),
    size=42, bold=True, color=WHITE)
section_header(sl, "📺", "Real-time Analytics at a Glance")

add_image(sl, IMG["dashboard"], Inches(0.55), Inches(1.7), width=Inches(10.2))

feats = [
    ("KPI Cards",      "Visitors · Conversion\nQueue · Abandonment"),
    ("Live Chart",     "Rolling time-series\nof visitors + queue"),
    ("Store Toggle",   "Switch between\nStore 1 & Store 2"),
    ("Auto-Refresh",   "Polls every 5s via\nfetch() API"),
]
for i, (t, b) in enumerate(feats):
    x = Inches(11.05)
    y = Inches(1.7 + i * 1.75)
    rect(sl, x, y, Inches(4.6), Inches(1.55), BG_CARD)
    rect(sl, x, y, Inches(0.07), Inches(1.55), PURPLE_VIVID)
    txt(sl, t, x + Inches(0.22), y + Inches(0.15), Inches(4.2), Inches(0.5),
        size=17, bold=True, color=PURPLE_LIGHT)
    txt(sl, b, x + Inches(0.22), y + Inches(0.65), Inches(4.2), Inches(0.8),
        size=15, color=GRAY_TEXT)

accent_bar(sl, SLIDE_H - Inches(0.06))
slide_number(sl, 5)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 6 — ZONE HEATMAP + CONVERSION FUNNEL
# ══════════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
bg(sl)
accent_bar(sl, 0)

txt(sl, "Zone Heatmap & Conversion Funnel",
    Inches(0.6), Inches(0.25), Inches(12), Inches(0.8),
    size=36, bold=True, color=WHITE)
section_header(sl, "🗺", "Understanding Where Customers Go")

add_image(sl, IMG["heatmap"], Inches(0.55), Inches(1.7), width=Inches(8.5))

txt(sl, "Zone Heatmap", Inches(9.4), Inches(1.7), Inches(6.2), Inches(0.6),
    size=22, bold=True, color=CYAN_ACCENT)
points = [
    "Color-coded grid of every product zone.",
    "Purple intensity = visit frequency.",
    "Hover tooltip: Visits count + Avg Dwell time.",
    "Identifies dead zones with zero traffic today.",
]
multiline(sl, points, Inches(9.4), Inches(2.35), Inches(6.2), Inches(2.5),
          size=18, color=GRAY_TEXT, bullet="›")

txt(sl, "Conversion Funnel (from dashboard)",
    Inches(9.4), Inches(4.9), Inches(6.2), Inches(0.6),
    size=22, bold=True, color=PURPLE_LIGHT)
funnel_pts = [
    "Entry  →  18 customers",
    "Zone Visit  →  6  (68.7% drop-off)",
    "Billing Queue  →  2  (68.7% drop-off)",
    "Purchase  →  0  (100% drop-off)",
]
multiline(sl, funnel_pts, Inches(9.4), Inches(5.55), Inches(6.2), Inches(2.5),
          size=18, color=GRAY_TEXT, bullet="▸")

accent_bar(sl, SLIDE_H - Inches(0.06))
slide_number(sl, 6)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 7 — REAL-TIME EVENT STREAM
# ══════════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
bg(sl)
accent_bar(sl, 0)

txt(sl, "Real-time Event Stream",
    Inches(0.6), Inches(0.25), Inches(12), Inches(0.8),
    size=42, bold=True, color=WHITE)
section_header(sl, "⚡", "Every Customer Move, Captured as an Event")

add_image(sl, IMG["events"], Inches(0.55), Inches(1.7), width=Inches(5.5))
add_image(sl, IMG["camera"], Inches(6.4), Inches(1.7), width=Inches(5.5))

event_types = [
    ("ENTRY / EXIT",           "Tracks door crossings, flags re-entries",   PURPLE_VIVID),
    ("ZONE_ENTER / EXIT",      "Captures product zone visits & dwell time",  CYAN_ACCENT),
    ("BILLING_QUEUE_JOIN",     "Detects customers joining checkout queue",   PURPLE_LIGHT),
    ("BILLING_QUEUE_ABANDON",  "Flags walk-outs before purchase",            RED_ACCENT),
]
for i, (ev, desc, col) in enumerate(event_types):
    x = Inches(12.2)
    y = Inches(1.8 + i * 1.75)
    rect(sl, x, y, Inches(3.5), Inches(1.55), BG_CARD)
    txt(sl, ev,   x + Inches(0.15), y + Inches(0.15), Inches(3.2), Inches(0.5),
        size=14, bold=True, color=col)
    txt(sl, desc, x + Inches(0.15), y + Inches(0.65), Inches(3.2), Inches(0.8),
        size=13, color=GRAY_TEXT)

accent_bar(sl, SLIDE_H - Inches(0.06))
slide_number(sl, 7)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 8 — ANOMALY DETECTION
# ══════════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
bg(sl)
accent_bar(sl, 0)

txt(sl, "Anomaly Detection",
    Inches(0.6), Inches(0.25), Inches(12), Inches(0.8),
    size=42, bold=True, color=WHITE)
section_header(sl, "🚨", "Proactive Operational Alerts in Real-Time")

add_image(sl, IMG["anomalies"], Inches(0.55), Inches(1.7), width=Inches(6.0))

txt(sl, "Three Anomaly Types", Inches(7.2), Inches(1.7), Inches(8.4), Inches(0.6),
    size=24, bold=True, color=PURPLE_LIGHT)

anomalies = [
    ("BILLING QUEUE SPIKE",
     "Queue > 5  →  WARN\nQueue > 10  →  CRITICAL\nAction: Deploy staff to checkout",
     RED_ACCENT),
    ("CONVERSION DROP",
     "Today < 70% of 7-day avg  →  WARN\nToday < 50% of 7-day avg  →  CRITICAL\nAction: Check POS / pricing issues",
     RED_ACCENT),
    ("DEAD ZONE",
     "No visits in 30+ min  →  WARN\nZero visits today  →  INFO\nAction: Review zone merchandising",
     PURPLE_VIVID),
]
for i, (title, body, col) in enumerate(anomalies):
    x = Inches(7.2)
    y = Inches(2.4 + i * 2.1)
    rect(sl, x, y, Inches(8.4), Inches(1.9), BG_CARD)
    rect(sl, x, y, Inches(0.07), Inches(1.9), col)
    txt(sl, title, x + Inches(0.22), y + Inches(0.15), Inches(8.0), Inches(0.5),
        size=17, bold=True, color=col)
    txt(sl, body,  x + Inches(0.22), y + Inches(0.65), Inches(8.0), Inches(1.1),
        size=15, color=GRAY_TEXT)

accent_bar(sl, SLIDE_H - Inches(0.06))
slide_number(sl, 8)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 9 — TECH STACK & SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
bg(sl)
accent_bar(sl, 0)

txt(sl, "Tech Stack & Impact",
    Inches(0.6), Inches(0.25), Inches(12), Inches(0.8),
    size=42, bold=True, color=WHITE)
section_header(sl, "🔧", "Built Lean. Works on CPU. Zero New Hardware.")

stack = [
    ("Detection",   "YOLOv8 Nano",     "CPU inference · 1 FPS · 93% frame skip"),
    ("Re-ID",       "HSV Histograms",  "Cosine similarity · No GPU required"),
    ("Backend",     "FastAPI + SQLite", "Zero-infra · Swagger UI · Full REST API"),
    ("Frontend",    "Vanilla JS + Chart.js", "No build step · Opens in browser"),
    ("Deployment",  "Docker Compose",  "Single command to run everything"),
]
for i, (cat, tech, detail) in enumerate(stack):
    x = Inches(0.55 + (i % 3) * 5.1)
    y = Inches(2.1 + (i // 3) * 2.5)
    rect(sl, x, y, Inches(4.8), Inches(2.1), BG_CARD)
    rect(sl, x, y, Inches(4.8), Inches(0.07), PURPLE_VIVID)
    txt(sl, cat,    x + Inches(0.2), y + Inches(0.2),  Inches(4.4), Inches(0.45),
        size=13, bold=True, color=GRAY_TEXT)
    txt(sl, tech,   x + Inches(0.2), y + Inches(0.65), Inches(4.4), Inches(0.55),
        size=20, bold=True, color=PURPLE_LIGHT)
    txt(sl, detail, x + Inches(0.2), y + Inches(1.2),  Inches(4.4), Inches(0.7),
        size=14, color=GRAY_TEXT)

# Impact callout bottom-right
rect(sl, Inches(10.6), Inches(2.1), Inches(5.1), Inches(4.6), BG_CARD)
rect(sl, Inches(10.6), Inches(2.1), Inches(5.1), Inches(0.07), CYAN_ACCENT)
txt(sl, "Key Outcomes", Inches(10.8), Inches(2.3), Inches(4.7), Inches(0.55),
    size=20, bold=True, color=CYAN_ACCENT)
outcomes = [
    "✅  Real-time visitor tracking",
    "✅  Zone dwell & conversion KPIs",
    "✅  Instant anomaly alerts",
    "✅  POS-correlated conversion rate",
    "✅  Works on existing CCTV + CPU",
    "✅  Live dashboard, no new hardware",
]
multiline(sl, outcomes, Inches(10.8), Inches(2.95), Inches(4.7), Inches(3.5),
          size=17, color=GRAY_TEXT, bullet="")

txt(sl, "Purplle Store Intelligence  ·  Hackathon 2026",
    Inches(0.6), Inches(8.5), Inches(10), Inches(0.4),
    size=12, color=GRAY_TEXT)

accent_bar(sl, SLIDE_H - Inches(0.06))
slide_number(sl, 9)

# ── Save ───────────────────────────────────────────────────────────────────────
out = r"d:\purple_hackathon\Purplle_Store_Intelligence_v2.pptx"
prs.save(out)
print(f"Saved: {out}")
