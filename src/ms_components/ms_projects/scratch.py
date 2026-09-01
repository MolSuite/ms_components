"""
Reflex/Vercel-style dark theme demo for PySide6
------------------------------------------------
Key structure:
- QFrame "outer-card" → outer border radius containing columns
- QFrame "col-card"   → inner columns with border-right and NO radius
- QPushButton "flat-link" → flat button with border-top and left-aligned text
- Grid background painted with QPainter (paintEvent)

Run: python reflex_theme_demo.py
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy
)
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontDatabase
from PySide6.QtCore import Qt, QSize


# ─── Color palette ────────────────────────────────────────────────────────────
BG          = "#0a0a0f"
GRID_LINE   = "rgba(255,255,255,0.04)"   # visual reference only
BORDER_SUB  = "#151520"   # very subtle border
BORDER_MID  = "#1e1e2e"   # medium border
TEXT_BRIGHT = "#e2e2e2"
TEXT_MID    = "#888899"
TEXT_DIM    = "#44445a"
ACCENT      = "#7c3aed"
ACCENT_DIM  = "rgba(124,58,237,0.15)"
WHITE       = "#ffffff"
BLACK       = "#000000"
SUCCESS_DIM = "rgba(74,222,128,0.15)"
SUCCESS     = "#4ade80"


# ─── QSS Global ───────────────────────────────────────────────────────────────
QSS = f"""
/* Reset base */
QWidget {{
    background: transparent;
    color: {TEXT_BRIGHT};
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 13px;
    border: none;
    outline: none;
}}

QScrollArea, QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_MID};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── Navbar ── */
QFrame#navbar {{
    background: rgba(10,10,15,0.9);
    border-bottom: 1px solid {BORDER_MID};
}}

QLabel#logo {{
    font-size: 15px;
    font-weight: bold;
    color: {WHITE};
    letter-spacing: 1px;
}}

QPushButton#nav-link {{
    color: {TEXT_MID};
    background: transparent;
    border: none;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
}}
QPushButton#nav-link:hover {{
    color: {WHITE};
    background: rgba(255,255,255,0.06);
}}

QPushButton#btn-ghost {{
    color: {TEXT_MID};
    background: transparent;
    border: 1px solid {BORDER_MID};
    padding: 6px 14px;
    border-radius: 7px;
    font-size: 13px;
}}
QPushButton#btn-ghost:hover {{
    color: {WHITE};
    border-color: rgba(255,255,255,0.25);
}}

QPushButton#btn-primary {{
    color: {BLACK};
    background: {WHITE};
    border: none;
    padding: 6px 16px;
    border-radius: 7px;
    font-size: 13px;
    font-weight: bold;
}}
QPushButton#btn-primary:hover {{
    background: #e0e0e0;
}}

/* ── Badge / chip ── */
QLabel#badge {{
    color: #a78bfa;
    background: rgba(139,92,246,0.15);
    border: 1px solid rgba(139,92,246,0.3);
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 11px;
}}

/* ── Hero typography ── */
QLabel#hero-title {{
    color: {WHITE};
    font-size: 36px;
    font-weight: bold;
    letter-spacing: -1px;
}}
QLabel#hero-subtitle {{
    color: {TEXT_MID};
    font-size: 14px;
    line-height: 1.6;
}}

/* ── Section label ── */
QLabel#section-label {{
    color: {TEXT_DIM};
    font-size: 10px;
    letter-spacing: 0.12em;
}}

/* ── Outer card (outer border radius, contains columns) ── */
QFrame#outer-card {{
    background: rgba(255,255,255,0.02);
    border: 1px solid {BORDER_MID};
    border-radius: 12px;
}}

/* ── Inner columns: straight border, NO radius ── */
QFrame#col-card {{
    background: transparent;
    border: none;
    border-right: 1px solid {BORDER_MID};
    border-radius: 0px;
    padding: 0px;
}}
QFrame#col-card-last {{
    background: transparent;
    border: none;
    border-radius: 0px;
    padding: 0px;
}}
QFrame#col-card:hover, QFrame#col-card-last:hover {{
    background: rgba(255,255,255,0.025);
}}

/* ── Icon inside the column ── */
QLabel#cell-icon {{
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    color: {TEXT_BRIGHT};
    font-size: 14px;
    padding: 6px;
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    qproperty-alignment: AlignCenter;
}}

QLabel#cell-title {{
    color: {TEXT_BRIGHT};
    font-size: 13px;
    font-weight: bold;
}}
QLabel#cell-desc {{
    color: {TEXT_MID};
    font-size: 12px;
}}

/* ── Flat link button (card footer) ── */
QPushButton#flat-link {{
    background: transparent;
    border: none;
    border-top: 1px solid {BORDER_MID};
    color: {TEXT_MID};
    font-size: 13px;
    text-align: left;
    padding: 14px 24px;
    border-radius: 0px;
}}
QPushButton#flat-link:hover {{
    color: {WHITE};
    background: rgba(255,255,255,0.025);
}}
QPushButton#flat-link-last {{
    background: transparent;
    border: none;
    border-top: 1px solid {BORDER_MID};
    border-left: 1px solid {BORDER_MID};
    color: {TEXT_MID};
    font-size: 13px;
    text-align: left;
    padding: 14px 24px;
    border-radius: 0px;
}}
QPushButton#flat-link-last:hover {{
    color: {WHITE};
    background: rgba(255,255,255,0.025);
}}

/* ── Pricing cards ── */
QFrame#pricing-outer {{
    background: rgba(255,255,255,0.02);
    border: 1px solid {BORDER_MID};
    border-radius: 12px;
}}
QFrame#pricing-col {{
    background: transparent;
    border: none;
    border-right: 1px solid {BORDER_MID};
    border-radius: 0px;
    padding: 28px 24px;
}}
QFrame#pricing-col-featured {{
    background: rgba(255,255,255,0.035);
    border: none;
    border-right: 1px solid {BORDER_MID};
    border-radius: 0px;
    padding: 28px 24px;
}}
QFrame#pricing-col-last {{
    background: transparent;
    border: none;
    border-radius: 0px;
    padding: 28px 24px;
}}

QLabel#plan-name {{
    color: {WHITE};
    font-size: 17px;
    font-weight: bold;
}}
QLabel#plan-desc {{
    color: {TEXT_MID};
    font-size: 12px;
}}
QLabel#plan-price {{
    color: {WHITE};
    font-size: 26px;
    font-weight: bold;
}}
QLabel#plan-price-sub {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
QLabel#plan-popular {{
    color: {BLACK};
    background: {WHITE};
    font-size: 10px;
    font-weight: bold;
    border-radius: 4px;
    padding: 2px 10px;
    letter-spacing: 0.06em;
}}

QLabel#feature-on {{
    color: {SUCCESS};
    background: {SUCCESS_DIM};
    border-radius: 10px;
    font-size: 10px;
    padding: 2px 6px;
    max-width: 18px;
    qproperty-alignment: AlignCenter;
}}
QLabel#feature-off {{
    color: {TEXT_DIM};
    background: rgba(255,255,255,0.04);
    border-radius: 10px;
    font-size: 10px;
    padding: 2px 6px;
    max-width: 18px;
    qproperty-alignment: AlignCenter;
}}
QLabel#feature-text {{
    color: {TEXT_MID};
    font-size: 12px;
}}

QPushButton#plan-btn {{
    background: transparent;
    border: 1px solid {BORDER_MID};
    color: {TEXT_MID};
    border-radius: 8px;
    padding: 9px 14px;
    font-size: 13px;
    text-align: left;
}}
QPushButton#plan-btn:hover {{
    border-color: rgba(255,255,255,0.25);
    color: {WHITE};
}}
QPushButton#plan-btn-featured {{
    background: {WHITE};
    border: none;
    color: {BLACK};
    border-radius: 8px;
    padding: 9px 14px;
    font-size: 13px;
    font-weight: bold;
    text-align: left;
}}
QPushButton#plan-btn-featured:hover {{
    background: #e0e0e0;
}}

/* ── Horizontal divider ── */
QFrame#hdivider {{
    background: {BORDER_MID};
    min-height: 1px;
    max-height: 1px;
    border: none;
}}

/* ── CTA bar ── */
QFrame#cta-bar {{
    background: rgba(255,255,255,0.02);
    border: 1px solid {BORDER_SUB};
    border-radius: 10px;
    padding: 0px;
}}
QLabel#cta-text {{
    color: {TEXT_MID};
    font-size: 13px;
}}
QLabel#cta-text-bold {{
    color: {WHITE};
    font-size: 13px;
    font-weight: bold;
}}
"""


# ─── Grid background widget ───────────────────────────────────────────────────
class GridBackground(QWidget):
    """Dark background with a Reflex-style point-and-line grid."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Solid background
        p.fillRect(self.rect(), QColor("#0a0a0f"))

        # Grid
        pen = QPen(QColor(255, 255, 255, 10))
        pen.setWidth(1)
        p.setPen(pen)

        step = 48
        w, h = self.width(), self.height()
        for x in range(0, w, step):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, step):
            p.drawLine(0, y, w, y)

        p.end()


# ─── Helpers ─────────────────────────────────────────────────────────────────
def lbl(text, obj_name="", parent=None):
    l = QLabel(text, parent)
    if obj_name:
        l.setObjectName(obj_name)
    l.setWordWrap(True)
    return l


def hdivider():
    d = QFrame()
    d.setObjectName("hdivider")
    d.setFixedHeight(1)
    d.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return d


def feature_row(text, active=True):
    row = QWidget()
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 3, 0, 3)
    hl.setSpacing(8)
    badge = lbl("✓" if active else "–", "feature-on" if active else "feature-off")
    badge.setFixedSize(18, 18)
    badge.setAlignment(Qt.AlignCenter)
    hl.addWidget(badge)
    hl.addWidget(lbl(text, "feature-text"))
    hl.addStretch()
    return row


# ─── Navbar ──────────────────────────────────────────────────────────────────
def make_navbar():
    bar = QFrame()
    bar.setObjectName("navbar")
    bar.setFixedHeight(52)

    hl = QHBoxLayout(bar)
    hl.setContentsMargins(24, 0, 24, 0)
    hl.setSpacing(0)

    logo = lbl("◆ AppDemo", "logo")
    hl.addWidget(logo)
    hl.addSpacing(32)

    for name in ["Platform", "Solutions", "Docs", "Pricing"]:
        btn = QPushButton(name)
        btn.setObjectName("nav-link")
        btn.setCursor(Qt.PointingHandCursor)
        hl.addWidget(btn)

    hl.addStretch()

    sign = QPushButton("Sign in")
    sign.setObjectName("btn-ghost")
    sign.setCursor(Qt.PointingHandCursor)
    hl.addWidget(sign)
    hl.addSpacing(8)

    start = QPushButton("Get started")
    start.setObjectName("btn-primary")
    start.setCursor(Qt.PointingHandCursor)
    hl.addWidget(start)

    return bar


# ─── Hero section ─────────────────────────────────────────────────────────────
def make_hero():
    w = QWidget()
    vl = QVBoxLayout(w)
    vl.setContentsMargins(0, 48, 0, 40)
    vl.setSpacing(12)

    badge = lbl("● Now in public beta", "badge")
    badge.setFixedWidth(160)
    vl.addWidget(badge)

    title = lbl("Build faster.\nShip with confidence.", "hero-title")
    title.setAlignment(Qt.AlignLeft)
    vl.addWidget(title)

    sub = lbl(
        "Deploy your apps in seconds. Scale automatically.\nBuilt for developers who move fast.",
        "hero-subtitle"
    )
    vl.addWidget(sub)
    vl.addSpacing(12)

    # Hero buttons
    btn_row = QWidget()
    hl = QHBoxLayout(btn_row)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(10)

    b1 = QPushButton("Start deploying  →")
    b1.setObjectName("btn-primary")
    b1.setCursor(Qt.PointingHandCursor)
    b1.setFixedHeight(36)

    b2 = QPushButton("View docs")
    b2.setObjectName("btn-ghost")
    b2.setCursor(Qt.PointingHandCursor)
    b2.setFixedHeight(36)

    hl.addWidget(b1)
    hl.addWidget(b2)
    hl.addStretch()
    vl.addWidget(btn_row)

    return w


# ─── Feature card (three Reflex-style columns) ────────────────────────────────
def make_feature_card():
    """
    Outer QFrame with a border radius.
    Inner QFrame columns with border-right but NO radius.
    Footer with flat-link QPushButtons.
    """
    outer = QFrame()
    outer.setObjectName("outer-card")

    vl_outer = QVBoxLayout(outer)
    vl_outer.setContentsMargins(0, 0, 0, 0)
    vl_outer.setSpacing(0)

    # Column row
    cols_widget = QWidget()
    hl = QHBoxLayout(cols_widget)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(0)

    data = [
        ("⚡", "Instant deploys",
         "Push to git and your app is live in under 10 seconds, globally distributed."),
        ("◎", "Edge network",
         "Your code runs at the edge, closest to each user. Zero cold starts."),
        ("⬡", "Observability",
         "Real-time logs, metrics and traces. See exactly what's happening."),
    ]

    for i, (icon, title, desc) in enumerate(data):
        is_last = (i == len(data) - 1)
        col = QFrame()
        col.setObjectName("col-card-last" if is_last else "col-card")
        col.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        cvl = QVBoxLayout(col)
        cvl.setContentsMargins(24, 24, 24, 24)
        cvl.setSpacing(10)

        icon_lbl = lbl(icon, "cell-icon")
        icon_lbl.setFixedSize(34, 34)
        icon_lbl.setAlignment(Qt.AlignCenter)
        cvl.addWidget(icon_lbl)

        cvl.addWidget(lbl(title, "cell-title"))
        cvl.addWidget(lbl(desc, "cell-desc"))
        cvl.addStretch()

        hl.addWidget(col)

    vl_outer.addWidget(cols_widget)

    # Footer with flat links
    footer = QWidget()
    fhl = QHBoxLayout(footer)
    fhl.setContentsMargins(0, 0, 0, 0)
    fhl.setSpacing(0)

    links = ["View use cases  →", "Get started in docs  →", "Explore hosting  →"]
    for i, text in enumerate(links):
        btn = QPushButton(text)
        # First: border-top plus border-right inherited from col-card.
        # Middle columns: border-left as well.
        # Use flat-link-last for columns without border-right.
        btn.setObjectName("flat-link" if i < len(links) - 1 else "flat-link-last")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setFixedHeight(48)
        fhl.addWidget(btn)

    vl_outer.addWidget(footer)
    return outer


# ─── Pricing cards ────────────────────────────────────────────────────────────
def make_pricing():
    w = QWidget()
    vl = QVBoxLayout(w)
    vl.setContentsMargins(0, 0, 0, 0)
    vl.setSpacing(12)

    outer = QFrame()
    outer.setObjectName("pricing-outer")

    hl = QHBoxLayout(outer)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(0)

    plans = [
        {
            "name": "Hobby", "desc": "The perfect starting point\nfor personal projects.",
            "price": "Free", "price_sub": "forever",
            "features": [
                (True, "100GB bandwidth/mo"),
                (True, "Automatic CI/CD"),
                (True, "Edge Functions"),
                (False, "Team collaboration"),
                (False, "Advanced analytics"),
            ],
            "btn": "Start deploying  →", "featured": False, "last": False,
        },
        {
            "name": "Pro", "desc": "Everything you need to\nbuild and scale.",
            "price": "$20", "price_sub": "/month",
            "features": [
                (True, "1TB bandwidth/mo"),
                (True, "Automatic CI/CD"),
                (True, "Edge Functions"),
                (True, "Team collaboration"),
                (True, "Advanced analytics"),
            ],
            "btn": "Start free trial  →", "featured": True, "last": False,
        },
        {
            "name": "Enterprise", "desc": "Critical security, SLAs\nand dedicated support.",
            "price": "Custom", "price_sub": "pricing",
            "features": [
                (True, "Unlimited bandwidth"),
                (True, "99.99% SLA"),
                (True, "SSO & SCIM"),
                (True, "Managed WAF"),
                (True, "Advanced support"),
            ],
            "btn": "Get a demo  →", "featured": False, "last": True,
        },
    ]

    for p in plans:
        if p["last"]:
            obj = "pricing-col-last"
        elif p["featured"]:
            obj = "pricing-col-featured"
        else:
            obj = "pricing-col"

        col = QFrame()
        col.setObjectName(obj)
        col.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        cvl = QVBoxLayout(col)
        cvl.setContentsMargins(24, 28, 24, 24)
        cvl.setSpacing(8)

        if p["featured"]:
            pop = lbl("POPULAR", "plan-popular")
            pop.setFixedWidth(70)
            cvl.addWidget(pop)
            cvl.addSpacing(4)

        cvl.addWidget(lbl(p["name"], "plan-name"))
        cvl.addWidget(lbl(p["desc"], "plan-desc"))
        cvl.addSpacing(4)

        price_row = QWidget()
        prl = QHBoxLayout(price_row)
        prl.setContentsMargins(0, 0, 0, 0)
        prl.setSpacing(4)
        prl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        prl.addWidget(lbl(p["price"], "plan-price"))
        sub = lbl(p["price_sub"], "plan-price-sub")
        sub.setAlignment(Qt.AlignBottom)
        prl.addWidget(sub)
        prl.addStretch()
        cvl.addWidget(price_row)

        cvl.addWidget(hdivider())

        for active, text in p["features"]:
            cvl.addWidget(feature_row(text, active))

        cvl.addStretch()
        cvl.addSpacing(8)

        btn_obj = "plan-btn-featured" if p["featured"] else "plan-btn"
        btn = QPushButton(p["btn"])
        btn.setObjectName(btn_obj)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(36)
        cvl.addWidget(btn)

        hl.addWidget(col)

    vl.addWidget(outer)

    # CTA bar
    cta = QFrame()
    cta.setObjectName("cta-bar")
    cta.setFixedHeight(52)
    chl = QHBoxLayout(cta)
    chl.setContentsMargins(20, 0, 20, 0)
    chl.setSpacing(6)

    chl.addWidget(lbl("Get started with v0.", "cta-text-bold"))
    chl.addWidget(lbl("Generate quality UI and ship end-to-end.", "cta-text"))
    chl.addStretch()

    cta_btn = QPushButton("Start building  →")
    cta_btn.setObjectName("btn-ghost")
    cta_btn.setCursor(Qt.PointingHandCursor)
    cta_btn.setFixedHeight(32)
    chl.addWidget(cta_btn)

    vl.addWidget(cta)
    return w


# ─── Main window ────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AppDemo – Reflex/Vercel theme")
        self.resize(1000, 800)
        self.setStyleSheet(QSS)

        # Grid background
        bg = GridBackground(self)
        self.setCentralWidget(bg)

        root_vl = QVBoxLayout(bg)
        root_vl.setContentsMargins(0, 0, 0, 0)
        root_vl.setSpacing(0)

        # Navbar pinned to the top
        root_vl.addWidget(make_navbar())

        # Content scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        root_vl.addWidget(scroll)

        # Centered inner container with max-width
        inner = QWidget()
        inner.setObjectName("inner")
        scroll.setWidget(inner)

        content_vl = QVBoxLayout(inner)
        content_vl.setContentsMargins(48, 0, 48, 48)
        content_vl.setSpacing(16)

        # Hero
        content_vl.addWidget(make_hero())

        # Section label + feature card
        sl = lbl("CORE FEATURES", "section-label")
        content_vl.addWidget(sl)
        content_vl.addWidget(make_feature_card())

        # Section label + pricing
        content_vl.addSpacing(24)
        sl2 = lbl("PRICING", "section-label")
        content_vl.addWidget(sl2)
        content_vl.addWidget(make_pricing())

        content_vl.addStretch()


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")   # neutral base; QSS takes full control

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
