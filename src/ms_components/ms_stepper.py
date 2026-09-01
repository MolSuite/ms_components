"""
qstepper.py
===========

Reusable *stepper* component for PySide6, modelled on Quasar's
(https://quasar.dev/vue-components/stepper).

It provides:
    - A header with indicators (number / prefix / icon / check / error) and
      connectors. HORIZONTAL or VERTICAL orientation (inline content).
    - Per-step states: inactive, active, done and error.
    - `alternative-labels` (horizontal): title/caption centred under the
      indicator. `inline-label` (vertical): title next to the indicator.
    - `prefix`: short text inside the indicator instead of the number.
    - Per-state icons: done / active / error, global and per step.
    - Per-step colours (active / done / inactive / error) over the base theme.
    - Validation hooks: each step may carry a validator that blocks advancing
      and marks the step as failed.
    - Programmatic navigation (next / previous / go_to) and header clicks
      (configurable per step).
    - Optional navigation bar (Back / Continue / Finish).
    - QSS-style theming: painted colours exposed as `qproperty-*`, and chrome
      (buttons, connectors, background) styleable by `objectName`. Example
      themes: light, dark, outlined and flat.
    - Signals: current_changed, step_changed, finished, validation_failed.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, List, Optional, Tuple, Union

from PySide6.QtCore import Qt, Signal, QSize, QRectF, QEvent, Property
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QIcon, QPainterPath, QPalette
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QPushButton, QSizePolicy, QApplication
)

from ms_components.theme import color

ColorLike = Union[QColor, str]
IconLike = Union[QIcon, str]            # QIcon, or a glyph/emoji
Validator = Callable[[], bool]          # returns True when the step is valid


# --------------------------------------------------------------------------- #
#  Enums y tema
# --------------------------------------------------------------------------- #
class StepState(Enum):
    INACTIVE = auto()
    ACTIVE = auto()
    DONE = auto()
    WARNING = auto()
    ERROR = auto()


class Orientation(Enum):
    HORIZONTAL = auto()
    VERTICAL = auto()


class StepperTheme:
    """Colours and metrics of the painted parts (indicators, connectors).

    The colours come from the live QPalette (and the theme's semantic accents),
    so they follow the active theme without anyone pinning them by hand.
    """

    def __init__(self) -> None:
        pal = QApplication.palette() if QApplication.instance() else QPalette()
        Role = QPalette.ColorRole
        self.primary = pal.color(Role.Highlight)
        self.done = pal.color(Role.Highlight)
        self.error = color("red")
        self.warning = color("orange")
        self.inactive = pal.color(Role.Mid)
        self.text_active = pal.color(Role.Highlight)
        self.text = pal.color(Role.Text)
        self.text_inactive = pal.color(Role.PlaceholderText)
        self.caption = pal.color(Role.PlaceholderText)
        self.connector = pal.color(Role.Mid)
        self.separator = pal.color(Role.Mid)
        self.indicator_text = pal.color(Role.HighlightedText)
        self.diameter = 28


def _qc(value: Optional[ColorLike]) -> Optional[QColor]:
    if value is None:
        return None
    return value if isinstance(value, QColor) else QColor(value)


# --------------------------------------------------------------------------- #
#  Indicator: a "dumb" painter that receives colour + content already resolved
# --------------------------------------------------------------------------- #
class _Indicator(QWidget):
    """Circle that paints a check, a text or an icon, as instructed."""

    def __init__(self, diameter: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._diameter = diameter
        self.fill = QColor("#9e9e9e")
        self.fg = QColor("#ffffff")
        self.mode = "text"           # 'text' | 'check' | 'icon'
        self.text = "1"
        self.qicon: Optional[QIcon] = None
        self.setFixedSize(diameter, diameter)

    def set_diameter(self, d: int) -> None:
        self._diameter = d
        self.setFixedSize(d, d)

    def sizeHint(self) -> QSize:
        return QSize(self._diameter, self._diameter)

    def set_content(self, *, fill: QColor, fg: QColor, mode: str,
                    text: str = "", qicon: Optional[QIcon] = None) -> None:
        self.fill, self.fg, self.mode = fill, fg, mode
        self.text, self.qicon = text, qicon
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = self._diameter
        rect = QRectF(0.5, 0.5, d - 1, d - 1)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self.fill))
        p.drawEllipse(rect)

        if self.mode == "check":
            self._draw_check(p, d / 2, d / 2, d / 2)
        elif self.mode == "icon" and self.qicon and not self.qicon.isNull():
            pix = self.qicon.pixmap(int(d * 0.6), int(d * 0.6))
            p.drawPixmap(int((d - pix.width()) / 2),
                         int((d - pix.height()) / 2), pix)
        else:  # text
            p.setPen(QPen(self.fg))
            f = QFont(self.font())
            f.setPointSizeF(max(8.0, d * 0.42))
            f.setBold(True)
            p.setFont(f)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()

    def _draw_check(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        pen = QPen(self.fg)
        pen.setWidthF(max(1.6, r * 0.16))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        path = QPainterPath()
        path.moveTo(cx - r * 0.40, cy + r * 0.02)
        path.lineTo(cx - r * 0.08, cy + r * 0.34)
        path.lineTo(cx + r * 0.44, cy - r * 0.30)
        p.drawPath(path)


# --------------------------------------------------------------------------- #
#  QStep: one step (data + content container)
# --------------------------------------------------------------------------- #
class QStep(QWidget):
    """
    One stepper step. A QWidget whose layout you fill with the content.

    Main parameters:
        title, caption   Header texts.
        icon             QIcon or glyph for the indicator (active / inactive).
        prefix           Short text inside the indicator instead of the number.
        name             Optional identifier (for go_to by name).
        disabled         Not navigable.
        header_nav       Allow navigating to this step by clicking the header.
        validator        Callable[[], bool]; returning False blocks advancing.
        done_icon/active_icon/error_icon
                         Per-state icons (QIcon or glyph). They override the
                         stepper's global ones.
        active_color/done_color/inactive_color/error_color
                         Per-step colours that override the theme.
    """

    changed = Signal()  # internal: asks the stepper to refresh

    def __init__(
        self,
        title: str = "",
        caption: str = "",
        icon: Optional[IconLike] = None,
        *,
        prefix: str = "",
        name: Optional[str] = None,
        disabled: bool = False,
        header_nav: bool = True,
        validator: Optional[Validator] = None,
        done_icon: Optional[IconLike] = None,
        active_icon: Optional[IconLike] = None,
        error_icon: Optional[IconLike] = None,
        active_color: Optional[ColorLike] = None,
        done_color: Optional[ColorLike] = None,
        inactive_color: Optional[ColorLike] = None,
        error_color: Optional[ColorLike] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.caption = caption
        self.icon = icon
        self.prefix = prefix
        self.name = name
        self.header_nav = header_nav
        self._disabled = disabled
        self._done = False
        self._error = False
        self._warning = False
        self._validator = validator

        self.done_icon = done_icon
        self.active_icon = active_icon
        self.error_icon = error_icon
        self.warning_icon = None
        self.active_color = _qc(active_color)
        self.done_color = _qc(done_color)
        self.inactive_color = _qc(inactive_color)
        self.error_color = _qc(error_color)
        self.warning_color = None

        self._body = QVBoxLayout(self)
        self._body.setContentsMargins(0, 8, 0, 0)
        self._body.setSpacing(8)

    # ---- contenido --------------------------------------------------------
    @property
    def body_layout(self) -> QVBoxLayout:
        return self._body

    def add_widget(self, widget: QWidget) -> QWidget:
        self._body.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._body.addLayout(layout)

    # ---- state ------------------------------------------------------------
    def set_done(self, value: bool = True) -> None:
        self._done = bool(value)
        if self._done:
            self._error = False
            self._warning = False
        self.changed.emit()

    def is_done(self) -> bool:
        return self._done

    def set_error(self, value: bool = True) -> None:
        self._error = bool(value)
        if self._error:
            self._done = False
            self._warning = False
        self.changed.emit()

    def has_error(self) -> bool:
        return self._error

    def set_warning(self, value: bool = True) -> None:
        self._warning = bool(value)
        if self._warning:
            self._done = False
            self._error = False
        self.changed.emit()

    def has_warning(self) -> bool:
        return self._warning

    def set_disabled(self, value: bool = True) -> None:
        self._disabled = bool(value)
        self.changed.emit()

    def is_disabled(self) -> bool:
        return self._disabled

    # ---- validation -------------------------------------------------------
    def set_validator(self, fn: Optional[Validator]) -> None:
        self._validator = fn

    def validate(self) -> bool:
        """True when the step is valid (or has no validator)."""
        if self._validator is None:
            return True
        try:
            return bool(self._validator())
        except Exception:
            return False


# --------------------------------------------------------------------------- #
#  Cabecera horizontal (normal o alternative-labels)
# --------------------------------------------------------------------------- #
class _HeaderItem(QWidget):
    clicked = Signal()

    def __init__(self, diameter: int, alternative: bool,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._navigable = False
        self.indicator = _Indicator(diameter)
        self.title_lbl = QLabel()
        self.caption_lbl = QLabel()
        self.title_lbl.setObjectName("stepperTitle")
        self.caption_lbl.setObjectName("stepperCaption")
        cf = QFont(self.caption_lbl.font())
        cf.setPointSizeF(max(8.0, cf.pointSizeF() - 1.5))
        self.caption_lbl.setFont(cf)

        if alternative:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(8, 0, 8, 4)
            lay.setSpacing(4)
            lay.addWidget(self.indicator, 0, Qt.AlignmentFlag.AlignHCenter)
            self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.caption_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(self.title_lbl)
            lay.addWidget(self.caption_lbl)
        else:
            lay = QHBoxLayout(self)
            lay.setContentsMargins(8, 4, 8, 4)
            lay.setSpacing(10)
            tbox = QVBoxLayout()
            tbox.setContentsMargins(0, 0, 0, 0)
            tbox.setSpacing(0)
            tbox.addWidget(self.title_lbl)
            tbox.addWidget(self.caption_lbl)
            lay.addWidget(self.indicator, 0, Qt.AlignmentFlag.AlignVCenter)
            lay.addLayout(tbox)

    def set_navigable(self, value: bool) -> None:
        self._navigable = value
        self.setCursor(Qt.CursorShape.PointingHandCursor if value
                       else Qt.CursorShape.ArrowCursor)

    def apply(self, step: QStep, title_color: QColor, bold: bool,
              caption_color: QColor) -> None:
        self.title_lbl.setText(step.title)
        self.caption_lbl.setText(step.caption)
        self.caption_lbl.setVisible(bool(step.caption))
        f = QFont(self.title_lbl.font())
        f.setBold(bold)
        self.title_lbl.setFont(f)
        self.title_lbl.setStyleSheet(f"color:{title_color.name()};")
        self.caption_lbl.setStyleSheet(f"color:{caption_color.name()};")
        self.setEnabled(not step.is_disabled())

    def mousePressEvent(self, event) -> None:
        if self._navigable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# --------------------------------------------------------------------------- #
#  Vertical rail: indicator + painted connector line
# --------------------------------------------------------------------------- #
class _VRail(QWidget):
    clicked = Signal()

    def __init__(self, diameter: int, connector: QColor,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._navigable = False
        self._d = diameter
        self._connector = connector
        self.indicator = _Indicator(diameter, self)
        self.is_last = False
        self.setFixedWidth(diameter + 16)
        self.setMinimumHeight(diameter)

    def set_connector(self, color: QColor) -> None:
        self._connector = color
        self.update()

    def set_navigable(self, value: bool) -> None:
        self._navigable = value
        self.setCursor(Qt.CursorShape.PointingHandCursor if value
                       else Qt.CursorShape.ArrowCursor)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2
        if not self.is_last:
            pen = QPen(self._connector)
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.drawLine(int(cx), self._d + 2, int(cx), self.height())
        p.end()

    def _place_indicator(self) -> None:
        self.indicator.move(int((self.width() - self._d) / 2), 0)

    def resizeEvent(self, event) -> None:
        self._place_indicator()
        super().resizeEvent(event)

    def showEvent(self, event) -> None:
        self._place_indicator()
        self.indicator.show()
        super().showEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._navigable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# --------------------------------------------------------------------------- #
#  QStepper
# --------------------------------------------------------------------------- #
class QStepper(QWidget):
    """
    Signals:
        current_changed(int)        index of the current step
        step_changed(QStep)         object of the current step
        finished()                  "Finish" was pressed (last step valid)
        validation_failed(QStep)    a step blocked advancing during validation
    """

    current_changed = Signal(int)
    step_changed = Signal(object)
    finished = Signal()
    validation_failed = Signal(object)

    def __init__(
        self,
        orientation: Orientation = Orientation.HORIZONTAL,
        theme: Optional[StepperTheme] = None,
        *,
        linear: bool = True,
        alternative_labels: bool = False,
        inline_label: bool = False,
        show_navigation: bool = True,
        auto_error_on_invalid: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("qStepper")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.theme = theme or StepperTheme()
        self.orientation = orientation
        self._linear = linear
        self.alternative_labels = alternative_labels
        self.inline_label = inline_label
        self._show_nav = show_navigation
        self._auto_error_on_invalid = auto_error_on_invalid

        # Global per-state icons (None => drawn fallback: check / "!").
        self.done_icon: Optional[IconLike] = None
        self.active_icon: Optional[IconLike] = None
        self.error_icon: Optional[IconLike] = None

        # TODO(responsive): implement Quasar's `contracted` mode. In horizontal
        # orientation, below a width threshold, hide titles/captions (or show
        # only the active step's label) and collapse the header to indicators
        # only. This would hook into resizeEvent to toggle a compact header
        # state. Not implemented yet.
        self.contracted = False  # placeholder, not yet implemented

        self._steps: List[QStep] = []
        self._current = -1
        self._max_reached = 0
        self._user_qss = ""

        self.back_text = "Back"
        self.next_text = "Continue"
        self.finish_text = "Finish"

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 5, 0, 0)
        self._root.setSpacing(0)

        self._build_navigation()
        self._apply_chrome()
        self._rebuild()
        # Set last: before this point changeEvent must not touch anything.
        self._auto_theme = theme is None

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and getattr(self, "_auto_theme", False):
            self.theme = StepperTheme()  # the default theme follows the live palette
            self._refresh_all()

    # =====================================================================
    #  QSS-style theming
    # =====================================================================
    #  The painted parts (indicators, lines) read from the theme. These
    #  properties let QSS change them via `qproperty-*`, e.g.:
    #
    #     QStepper { qproperty-primaryColor: #90caf9;
    #                qproperty-connectorColor: #555; background: #1e1e1e; }
    #
    #  The "chrome" (buttons, connectors, background) is styled by objectName.
    # ---------------------------------------------------------------------
    def _set_theme_color(self, attr: str, c: ColorLike) -> bool:
        c = QColor(c)
        if getattr(self.theme, attr) == c:
            return False
        setattr(self.theme, attr, c)
        return True

    def _refresh_all(self) -> None:
        self._apply_chrome()
        self._refresh_headers()

    def _get_primary(self): return self.theme.primary
    def _set_primary(self, c):
        if self._set_theme_color("primary", c):
            self.theme.done = QColor(c)
            self._refresh_all()
    primaryColor = Property(QColor, _get_primary, _set_primary)

    def _get_error(self): return self.theme.error
    def _set_error(self, c):
        if self._set_theme_color("error", c):
            self._refresh_headers()
    errorColor = Property(QColor, _get_error, _set_error)

    def _get_inactive(self): return self.theme.inactive
    def _set_inactive(self, c):
        if self._set_theme_color("inactive", c):
            self._refresh_headers()
    inactiveColor = Property(QColor, _get_inactive, _set_inactive)

    def _get_connector(self): return self.theme.connector
    def _set_connector(self, c):
        if self._set_theme_color("connector", c):
            self._refresh_all()
            for r in getattr(self, "_rails", []):
                r.set_connector(self.theme.connector)
    connectorColor = Property(QColor, _get_connector, _set_connector)

    def _get_text(self): return self.theme.text
    def _set_text(self, c):
        if self._set_theme_color("text", c):
            self._refresh_headers()
    textColor = Property(QColor, _get_text, _set_text)

    def _get_text_active(self): return self.theme.text_active
    def _set_text_active(self, c):
        if self._set_theme_color("text_active", c):
            self._refresh_headers()
    textActiveColor = Property(QColor, _get_text_active, _set_text_active)

    def _get_text_inactive(self): return self.theme.text_inactive
    def _set_text_inactive(self, c):
        if self._set_theme_color("text_inactive", c):
            self._refresh_headers()
    textInactiveColor = Property(QColor, _get_text_inactive, _set_text_inactive)

    def _get_caption(self): return self.theme.caption
    def _set_caption(self, c):
        if self._set_theme_color("caption", c):
            self._refresh_headers()
    captionColor = Property(QColor, _get_caption, _set_caption)

    def _get_indicator_text(self): return self.theme.indicator_text
    def _set_indicator_text(self, c):
        if self._set_theme_color("indicator_text", c):
            self._refresh_headers()
    indicatorTextColor = Property(QColor, _get_indicator_text, _set_indicator_text)

    def set_qss(self, qss: str) -> None:
        """Append user QSS on top of the stepper's default chrome."""
        self._user_qss = qss or ""
        self._apply_chrome()

    def _apply_chrome(self) -> None:
        t = self.theme
        primary = t.primary.name()
        primary_dark = t.primary.darker(112).name()
        base = f"""
        QPushButton#stepperNext {{
            background:{primary}; color:palette(highlighted-text); border:none;
            padding:8px 18px; border-radius:4px; font-weight:600;
        }}
        QPushButton#stepperNext:hover {{ background:{primary_dark}; }}
        QPushButton#stepperNext:disabled {{
            background:palette(mid); color:palette(placeholder-text);
        }}
        QPushButton#stepperBack {{
            background:transparent; color:palette(text); border:none;
            padding:8px 14px; border-radius:4px; font-weight:600;
        }}
        QPushButton#stepperBack:hover {{ background:palette(alternate-base); }}
        QPushButton#stepperBack:disabled {{ color:palette(placeholder-text); }}
        QFrame#stepperConnector {{
            background:{t.connector.name()}; max-height:2px; border:none;
        }}
        QFrame#stepperSeparator {{
            background:{t.separator.name()}; max-height:1px; border:none;
        }}
        """
        self.setStyleSheet(base + "\n" + self._user_qss)

    # =====================================================================
    #  Navigation bar
    # =====================================================================
    def _build_navigation(self) -> None:
        self._nav = QFrame()
        self._nav.setObjectName("stepperNav")
        lay = QHBoxLayout(self._nav)
        lay.setContentsMargins(0, 12, 0, 0)
        self.btn_back = QPushButton(self.back_text)
        self.btn_next = QPushButton(self.next_text)
        self.btn_back.setObjectName("stepperBack")
        self.btn_next.setObjectName("stepperNext")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.previous)
        self.btn_next.clicked.connect(self._on_next_clicked)
        lay.addWidget(self.btn_back)
        lay.addStretch(1)
        lay.addWidget(self.btn_next)
        self._nav.setVisible(self._show_nav)

    # =====================================================================
    #  Public API
    # =====================================================================
    def add_step(self, title: Union[str, QStep] = "", caption: str = "",
                 icon: Optional[IconLike] = None, **kwargs) -> QStep:
        step = title if isinstance(title, QStep) else QStep(
            title, caption, icon, **kwargs)
        step.changed.connect(self._refresh_headers)
        self._steps.append(step)
        self._rebuild()
        if self._current == -1:
            self.set_current_index(0)
        return step

    def steps(self) -> List[QStep]:
        return list(self._steps)

    def count(self) -> int:
        return len(self._steps)

    @property
    def current_index(self) -> int:
        return self._current

    def current_step(self) -> Optional[QStep]:
        if 0 <= self._current < len(self._steps):
            return self._steps[self._current]
        return None

    def set_current_index(self, index: int) -> None:
        """Navigate without validating (programmatic use)."""
        if not (0 <= index < len(self._steps)):
            return
        if self._steps[index].is_disabled():
            return
        self._current = index
        self._max_reached = max(self._max_reached, index)
        self._sync_content()
        self._refresh_headers()
        self._refresh_nav()
        self.current_changed.emit(index)
        self.step_changed.emit(self._steps[index])

    def go_to(self, ref: Union[int, str, QStep]) -> None:
        if isinstance(ref, int):
            self.set_current_index(ref)
        elif isinstance(ref, QStep) and ref in self._steps:
            self.set_current_index(self._steps.index(ref))
        elif isinstance(ref, str):
            for i, s in enumerate(self._steps):
                if s.name == ref:
                    self.set_current_index(i)
                    return

    def next(self) -> None:
        """Validate the current step and, if it passes, mark it done and advance."""
        if not self._leave_current_ok():
            return
        cur = self.current_step()
        if cur and not cur.has_error():
            cur.set_done(True)
        j = self._current + 1
        while j < len(self._steps) and self._steps[j].is_disabled():
            j += 1
        if j < len(self._steps):
            self.set_current_index(j)

    def previous(self) -> None:
        j = self._current - 1
        while j >= 0 and self._steps[j].is_disabled():
            j -= 1
        if j >= 0:
            self.set_current_index(j)

    def set_navigation_visible(self, value: bool) -> None:
        self._show_nav = value
        self._nav.setVisible(value)

    # =====================================================================
    #  Validation
    # =====================================================================
    def _leave_current_ok(self) -> bool:
        cur = self.current_step()
        if cur is None:
            return True
        if cur.validate():
            if self._auto_error_on_invalid and cur.has_error():
                cur.set_error(False)
            return True
        if self._auto_error_on_invalid:
            cur.set_error(True)
        self.validation_failed.emit(cur)
        return False

    # =====================================================================
    #  Layout construction
    # =====================================================================
    def _clear_root(self) -> None:
        while self._root.count():
            item = self._root.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._nav:
                w.setParent(None)

    def _rebuild(self) -> None:
        for step in self._steps:
            step.setParent(None)
        self._clear_root()
        self._header_items: List[_HeaderItem] = []
        self._rails: List[_VRail] = []

        if self.orientation == Orientation.HORIZONTAL:
            self._build_horizontal()
        else:
            self._build_vertical()

        self._root.addWidget(self._nav)
        self._refresh_headers()
        self._refresh_nav()
        if 0 <= self._current < len(self._steps):
            self._sync_content()

    def _make_hconnector(self) -> QWidget:
        line = QFrame()
        line.setObjectName("stepperConnector")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        line.setFixedHeight(2)
        if not self.alternative_labels:
            return line
        # alternative-labels: align the line with the centre of the indicator.
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addSpacing(self.theme.diameter // 2 - 1)
        v.addWidget(line)
        v.addStretch(1)
        return wrap

    def _build_horizontal(self) -> None:
        header = QFrame()
        header.setObjectName("stepperHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        align = (Qt.AlignmentFlag.AlignTop if self.alternative_labels
                 else Qt.AlignmentFlag.AlignVCenter)

        for i, step in enumerate(self._steps):
            item = _HeaderItem(self.theme.diameter, self.alternative_labels)
            item.clicked.connect(lambda idx=i: self._on_header_clicked(idx))
            self._header_items.append(item)
            h.addWidget(item, 0, align)
            if i < len(self._steps) - 1:
                conn = self._make_hconnector()
                h.addWidget(conn, 1, align if self.alternative_labels
                            else Qt.AlignmentFlag.AlignVCenter)

        self._root.addWidget(header)

        sep = QFrame()
        sep.setObjectName("stepperSeparator")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        self._root.addWidget(sep)

        self._stack = QStackedWidget()
        for step in self._steps:
            self._stack.addWidget(step)
        self._root.addWidget(self._stack, 1)

    def _build_vertical(self) -> None:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        for i, step in enumerate(self._steps):
            block = QWidget()
            row = QHBoxLayout(block)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            rail = _VRail(self.theme.diameter, self.theme.connector)
            rail.clicked.connect(lambda idx=i: self._on_header_clicked(idx))
            self._rails.append(rail)

            right = QVBoxLayout()
            right.setContentsMargins(0, 0, 0, 0)
            right.setSpacing(2)

            title_lbl = QLabel(step.title)
            caption_lbl = QLabel(step.caption)
            title_lbl.setObjectName("stepperTitle")
            caption_lbl.setObjectName("stepperCaption")
            cf = QFont(caption_lbl.font())
            cf.setPointSizeF(max(8.0, cf.pointSizeF() - 1.5))
            caption_lbl.setFont(cf)
            caption_lbl.setVisible(bool(step.caption))
            rail._title_lbl = title_lbl      # type: ignore[attr-defined]
            rail._caption_lbl = caption_lbl  # type: ignore[attr-defined]

            if self.inline_label:
                head = QHBoxLayout()
                head.setContentsMargins(0, 0, 0, 0)
                head.setSpacing(8)
                head.addWidget(title_lbl)
                head.addWidget(caption_lbl)
                head.addStretch(1)
                right.addLayout(head)
            else:
                right.addWidget(title_lbl)
                right.addWidget(caption_lbl)
            right.addWidget(step)

            row.addWidget(rail, 0, Qt.AlignmentFlag.AlignTop)
            row.addLayout(right, 1)
            v.addWidget(block)

        v.addStretch(1)
        self._root.addWidget(container, 1)

    # =====================================================================
    #  State / colour refresh
    # =====================================================================
    def _state_for(self, index: int, step: QStep) -> StepState:
        # ACTIVE wins: while you're on a step it stays neutral/active; the done/warning/error
        # marking only surfaces once you move to another step.
        if index == self._current:
            return StepState.ACTIVE
        if step.has_error():
            return StepState.ERROR
        if step.has_warning():
            return StepState.WARNING
        if step.is_done():
            return StepState.DONE
        return StepState.INACTIVE

    def _fill_color(self, step: QStep, state: StepState) -> QColor:
        if state == StepState.ERROR:
            return step.error_color or self.theme.error
        if state == StepState.WARNING:
            return step.warning_color or self.theme.warning
        if state == StepState.ACTIVE:
            return step.active_color or self.theme.primary
        if state == StepState.DONE:
            return step.done_color or self.theme.done
        return step.inactive_color or self.theme.inactive

    def _title_style(self, step: QStep, state: StepState) -> Tuple[QColor, bool]:
        if state == StepState.ACTIVE:
            return (step.active_color or self.theme.text_active, True)
        if state == StepState.ERROR:
            return (step.error_color or self.theme.error, True)
        if state == StepState.WARNING:
            return (step.warning_color or self.theme.warning, True)
        if state == StepState.DONE:
            return (self.theme.text, False)
        return (step.inactive_color or self.theme.text_inactive, False)

    def _as_qicon(self, ico: IconLike) -> Optional[QIcon]:
        return ico if isinstance(ico, QIcon) else None

    def _resolve_indicator(self, step: QStep, number: int,
                           state: StepState) -> Tuple[str, str, Optional[QIcon]]:
        """Return (mode, text, qicon) for the indicator."""
        if state == StepState.ERROR:
            ico = step.error_icon or self.error_icon
            if ico is None:
                return ("text", "✕", None)
            return ("icon", "", self._as_qicon(ico)) if isinstance(ico, QIcon) \
                else ("text", str(ico), None)
        if state == StepState.WARNING:
            ico = step.warning_icon
            if ico is None:
                return ("text", "⚠", None)
            return ("icon", "", self._as_qicon(ico)) if isinstance(ico, QIcon) \
                else ("text", str(ico), None)
        if state == StepState.DONE:
            ico = step.done_icon or self.done_icon
            if ico is None:
                return ("check", "", None)
            return ("icon", "", self._as_qicon(ico)) if isinstance(ico, QIcon) \
                else ("text", str(ico), None)
        if state == StepState.ACTIVE:
            ico = step.active_icon or self.active_icon or step.icon
        else:
            ico = step.icon
        if ico is not None:
            return ("icon", "", self._as_qicon(ico)) if isinstance(ico, QIcon) \
                else ("text", str(ico), None)
        if step.prefix:
            return ("text", step.prefix, None)
        return ("text", str(number), None)

    def _refresh_headers(self) -> None:
        horizontal = self.orientation == Orientation.HORIZONTAL
        for i, step in enumerate(self._steps):
            state = self._state_for(i, step)
            fill = self._fill_color(step, state)
            mode, text, qicon = self._resolve_indicator(step, i + 1, state)
            tcolor, bold = self._title_style(step, state)
            nav = self._can_navigate_to(i)

            if horizontal and self._header_items:
                item = self._header_items[i]
                item.indicator.set_content(fill=fill, fg=self.theme.indicator_text,
                                           mode=mode, text=text, qicon=qicon)
                item.apply(step, tcolor, bold, self.theme.caption)
                item.set_navigable(nav)
            elif self._rails:
                rail = self._rails[i]
                rail.is_last = (i == len(self._steps) - 1)
                rail.set_connector(self.theme.connector)
                rail.indicator.set_content(fill=fill, fg=self.theme.indicator_text,
                                           mode=mode, text=text, qicon=qicon)
                rail.set_navigable(nav)
                t = rail._title_lbl       # type: ignore[attr-defined]
                c = rail._caption_lbl     # type: ignore[attr-defined]
                f = QFont(t.font()); f.setBold(bold); t.setFont(f)
                t.setStyleSheet(f"color:{tcolor.name()};")
                c.setStyleSheet(f"color:{self.theme.caption.name()};")
                step.setVisible(i == self._current)

    def _can_navigate_to(self, index: int) -> bool:
        step = self._steps[index]
        if step.is_disabled() or not step.header_nav:
            return False
        if not self._linear:
            return True
        return index <= self._max_reached or step.is_done()

    def _sync_content(self) -> None:
        if self.orientation == Orientation.HORIZONTAL and hasattr(self, "_stack"):
            self._stack.setCurrentIndex(self._current)
        else:
            for i, step in enumerate(self._steps):
                step.setVisible(i == self._current)

    def _refresh_nav(self) -> None:
        if not self._steps:
            self.btn_back.setEnabled(False)
            self.btn_next.setEnabled(False)
            return
        self.btn_back.setEnabled(self._current > 0)
        is_last = self._current == len(self._steps) - 1
        self.btn_next.setText(self.finish_text if is_last else self.next_text)
        self.btn_next.setEnabled(True)

    # =====================================================================
    #  Slots
    # =====================================================================
    def _on_header_clicked(self, index: int) -> None:
        if not self._can_navigate_to(index):
            return
        if index > self._current and not self._leave_current_ok():
            return
        self.set_current_index(index)

    def _on_next_clicked(self) -> None:
        if self._current == len(self._steps) - 1:
            if not self._leave_current_ok():
                return
            cur = self.current_step()
            if cur and not cur.has_error():
                cur.set_done(True)
            self._refresh_headers()
            self.finished.emit()
        else:
            self.next()


# --------------------------------------------------------------------------- #
#  Example QSS themes (light by default; apply these with set_qss)
# --------------------------------------------------------------------------- #
DARK_QSS = """
QStepper {
    qproperty-primaryColor: #90caf9;
    qproperty-connectorColor: #555555;
    qproperty-inactiveColor: #5a5a5a;
    qproperty-textColor: #e0e0e0;
    qproperty-textInactiveColor: #888888;
    qproperty-captionColor: #9e9e9e;
    qproperty-indicatorTextColor: #0d1117;
    background: #1e1e1e;
}
QStepper QPushButton#stepperBack { color: #cfcfcf; }
QStepper QFrame#stepperSeparator { background: #3a3a3a; }
"""

BORDERED_QSS = """
QStepper {
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
}
"""

FLAT_QSS = """
QStepper QPushButton#stepperNext {
    background: transparent;
    color: palette(highlight);
    font-weight: 700;
}
QStepper QPushButton#stepperNext:hover { background: rgba(25,118,210,0.10); }
"""


# --------------------------------------------------------------------------- #
#  Demo
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QLineEdit, QFormLayout, QCheckBox,
        QComboBox, QHBoxLayout as _H, QPushButton as _B
    )

    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle("QStepper - demo")
    win.resize(680, 480)

    central = QWidget()
    outer = QVBoxLayout(central)

    stepper = QStepper(
        orientation=Orientation.HORIZONTAL,
        linear=True,
        alternative_labels=True,   # try False for the classic mode
    )

    # Step 1 with validation: the email may not be empty.
    s1 = stepper.add_step("Account", "Sign-in details", icon="\u2709")
    email = QLineEdit(); email.setPlaceholderText("you@example.com")
    pwd = QLineEdit(); pwd.setEchoMode(QLineEdit.EchoMode.Password)
    f1 = QFormLayout(); f1.addRow("Email:", email); f1.addRow("Password:", pwd)
    s1.add_layout(f1)
    s1.set_validator(lambda: bool(email.text().strip()))

    # Step 2 with its own prefix and colour.
    s2 = stepper.add_step("Profile", "Tell us about yourself",
                          prefix="2A", active_color="#6a1b9a")
    f2 = QFormLayout(); f2.addRow("Name:", QLineEdit())
    combo = QComboBox(); combo.addItems(["Colombia", "Mexico", "Spain"])
    f2.addRow("Country:", combo)
    s2.add_layout(f2)

    # Step 3.
    s3 = stepper.add_step("Confirm", "Review and finish")
    s3.add_widget(QLabel("All good? Press Finish."))
    s3.add_widget(QCheckBox("I accept the terms and conditions"))

    hint = QLabel(); hint.setStyleSheet("color:#c10015;")
    s1.add_widget(hint)
    stepper.validation_failed.connect(
        lambda step: hint.setText("Email is required.")
        if step is s1 else None)
    email.textChanged.connect(lambda *_: hint.setText(""))

    stepper.finished.connect(
        lambda: stepper.btn_next.setEnabled(False))

    # Button that toggles the dark theme (QSS-style theming).
    bar = _H()
    btn_dark = _B("Dark theme")
    _dark = {"on": False}
    def toggle_dark():
        _dark["on"] = not _dark["on"]
        stepper.set_qss(DARK_QSS if _dark["on"] else "")
    btn_dark.clicked.connect(toggle_dark)
    bar.addStretch(1); bar.addWidget(btn_dark)

    outer.addLayout(bar)
    outer.addWidget(stepper)
    win.setCentralWidget(central)
    win.show()
    sys.exit(app.exec())