"""Tool panel: the frame every configure-then-run tool shares.

    ┌ top bar ──── scope and context; created on first use ─────┐
    │ body ─────── sections, free widgets, Advanced (scrolls)   │
    └ action bar ─ summary or progress · actions; first use ────┘

UI only: it knows nothing about jobs or runtimes. The host maps its job events onto
``ActionBar.start / set_progress / finish``. The status bar and the job monitor keep the
full detail, so the progress here is deliberately a quiet 3 px line.

Inside a QStepper, put one panel per step (``step.add_widget(panel)`` with the step's
``body_layout`` margins at 0): each step keeps its own bar state while hidden, so there is
nothing to swap when the current step changes.

Dividers and rules are painted with the palette, not styled: the panel follows the theme
without any rule in ``base.qss``.
"""

from __future__ import annotations

import html
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ms_components import theme

_clock = time.monotonic  # module-level so tests can drive time
_NARROW_NBSP = " "
_INDENT = 12
#: Object names styled in base.qss; no inline stylesheets, so themes stay in charge.
PROGRESS_NAME = "ToolProgress"
SECTION_TOGGLE_NAME = "SectionToggle"


def format_count(value: int) -> str:
    """12480 -> '12 480' with a narrow no-break space, so a count never wraps mid-number."""
    return f"{int(value):,}".replace(",", _NARROW_NBSP)


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return ""
    if seconds < 60:
        return "< 1 min left"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"≈ {minutes} min left"
    hours, minutes = divmod(minutes, 60)
    return f"≈ {hours} h {minutes} min left" if minutes else f"≈ {hours} h left"


def hint_label(text: str, parent: QWidget | None = None) -> QLabel:
    """Secondary text (method notes, section descriptions): caption size, placeholder colour."""
    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setFont(theme.font("caption"))
    label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
    return label


class _Rule(QWidget):
    """A 1 px palette(mid) line centred in its height."""

    def __init__(self, height: int = 1, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.Mid))
        y = self.height() // 2
        painter.drawLine(0, y, self.width(), y)


class ContentBar(QFrame):
    """Full-width strip with a divider on one edge. The padding lives inside, so the
    background and the divider reach the panel edges."""

    def __init__(self, divider: Qt.Edge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._divider = divider
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(12, 8, 12, 8)
        self.row.setSpacing(6)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.row.addWidget(widget, stretch)
        return widget

    def add_label(self, text: str, buddy: QWidget | None = None) -> QLabel:
        label = QLabel(text, self)
        if buddy is not None:
            label.setBuddy(buddy)
        self.row.addWidget(label)
        return label

    def add_stretch(self) -> None:
        self.row.addStretch(1)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.Mid))
        y = self.height() - 1 if self._divider == Qt.Edge.BottomEdge else 0
        painter.drawLine(0, y, self.width(), y)


class ToolSection(QWidget):
    """One flat section: a header (title + rule) over a form body.

    checkable    The title is a checkbox. Unchecked disables the body (checkable QGroupBox
                 semantics), or hides it with ``collapse_when_unchecked`` for large
                 optional bodies (flexible residues).
    collapsible  The title is a disclosure arrow, for options few people need (Advanced).

    ``isChecked / setChecked / toggled`` mirror QGroupBox, so code written against a
    checkable group box keeps working.
    """

    toggled = Signal(bool)
    expanded_changed = Signal(bool)

    def __init__(
        self,
        title: str,
        *,
        description: str = "",
        checkable: bool = False,
        checked: bool = True,
        collapse_when_unchecked: bool = False,
        collapsible: bool = False,
        expanded: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        if checkable and collapsible:
            raise ValueError("a section is either checkable or collapsible, not both")
        super().__init__(parent)
        self._title = title
        self._collapsible = collapsible
        self._collapse_when_unchecked = collapse_when_unchecked
        self._expanded = expanded or not collapsible
        self._checkbox: QCheckBox | None = None
        self._arrow: QToolButton | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        header = QHBoxLayout()
        header.setSpacing(8)
        if checkable:
            self._checkbox = QCheckBox(title, self)
            self._checkbox.setChecked(checked)
            self._checkbox.toggled.connect(self._on_toggled)
            title_widget: QWidget = self._checkbox
        elif collapsible:
            self._arrow = QToolButton(self)
            self._arrow.setText(title)
            self._arrow.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            # base.qss drops the tool-button frame for this name: a heading, not a button.
            self._arrow.setObjectName(SECTION_TOGGLE_NAME)
            self._arrow.clicked.connect(lambda: self.setExpanded(not self._expanded))
            title_widget = self._arrow
        else:
            title_widget = QLabel(title, self)
        self._title_widget = title_widget
        title_widget.setFont(theme.font("strong"))
        header.addWidget(title_widget)
        header.addWidget(_Rule(parent=self), 1)
        outer.addLayout(header)

        self.description = hint_label(description, self)
        self.description.setContentsMargins(_INDENT, 0, 0, 0)
        outer.addWidget(self.description)

        self.body = QWidget(self)
        self.form = QFormLayout(self.body)
        self.form.setContentsMargins(_INDENT, 0, 0, 0)
        # Fields keep their natural width: a pH box stretched to 900 px stops reading as a form.
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        # Left-aligned: labels share the left edge of the description and the spanning rows.
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(self.body)
        self._sync()

    def add_row(self, *args) -> None:
        """``QFormLayout.addRow`` overloads: (label, field), (widget) spanning, (layout)."""
        self.form.addRow(*args)

    def title(self) -> str:
        return self._title

    def setTitle(self, title: str) -> None:
        self._title = title
        self._title_widget.setText(title)

    def isChecked(self) -> bool:
        return self._checkbox.isChecked() if self._checkbox is not None else True

    def setChecked(self, checked: bool) -> None:
        if self._checkbox is not None:
            self._checkbox.setChecked(checked)

    def isExpanded(self) -> bool:
        return self._expanded

    def setExpanded(self, expanded: bool) -> None:
        if not self._collapsible or expanded == self._expanded:
            return
        self._expanded = expanded
        self._sync()
        self.expanded_changed.emit(expanded)

    def _on_toggled(self, checked: bool) -> None:
        self._sync()
        self.toggled.emit(checked)

    def _sync(self) -> None:
        on = self.isChecked()
        visible = self._expanded and (on or not self._collapse_when_unchecked)
        for part in (self.description, self.body):
            part.setEnabled(on)
        self.body.setVisible(visible)
        self.description.setVisible(visible and bool(self.description.text()))
        if self._arrow is not None:
            self._arrow.setArrowType(Qt.ArrowType.DownArrow if self._expanded else Qt.ArrowType.RightArrow)


class ActionBar(ContentBar):
    """Bottom strip: a summary while idle, a quiet progress line while running, and the
    tool's actions on the right.

    Run-type actions give way to Cancel while running. The actions area keeps its idle
    width meanwhile, so the text and the progress line on the left never jump.
    """

    cancel_requested = Signal()
    details_requested = Signal()
    busy_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Edge.TopEdge, parent)
        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(4)
        self.headline = QLabel(self)
        self.headline.setTextFormat(Qt.TextFormat.PlainText)
        self.progress = QProgressBar(self)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.setObjectName(PROGRESS_NAME)
        self.progress.hide()
        self._rule = _Rule(3, self)  # holds the progress line's slot while idle
        self.detail = hint_label("", self)
        self.detail.setWordWrap(False)
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        self.detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self.detail.linkActivated.connect(lambda _link: self.details_requested.emit())
        for widget in (self.headline, self.progress, self._rule, self.detail):
            info.addWidget(widget)
        self.row.addLayout(info, 2)
        self.row.addStretch(1)

        self._actions_box = QWidget(self)
        self._actions = QHBoxLayout(self._actions_box)
        self._actions.setContentsMargins(0, 0, 0, 0)
        self._actions.setSpacing(6)
        self._actions.addStretch(1)
        self.cancel_button = QPushButton("Cancel", self._actions_box)
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self._on_cancel)
        self._actions.addWidget(self.cancel_button)
        self.row.addWidget(self._actions_box)

        self._run_actions: list[QWidget] = []
        self._restore: list[QWidget] = []
        self._running = False
        self._rate_origin: tuple[float, int] | None = None  # (time, done) the ETA rate counts from

    @property
    def is_running(self) -> bool:
        return self._running

    def add_action(self, widget: QWidget, *, hide_while_running: bool = True) -> QWidget:
        """Any button (plain, split, menu). ``hide_while_running=False`` for actions that
        stay useful during a run, such as Open Results."""
        self._actions.insertWidget(self._actions.indexOf(self.cancel_button), widget)
        if hide_while_running:
            self._run_actions.append(widget)
        return widget

    def set_summary(self, headline: str, detail: str = "") -> None:
        """Idle text: what a run would cover (scope counts, estimate)."""
        self._set_running(False)
        self._show(headline, detail)

    def start(self, headline: str = "Running…", detail: str = "") -> None:
        """Running with unknown progress: submitted, waiting for prerequisites."""
        self._set_running(True)
        self._rate_origin = None  # time spent waiting says nothing about the processing rate
        self.progress.setRange(0, 0)
        self._show(headline, detail)

    def set_progress(
        self,
        done: int,
        total: int | None = None,
        *,
        stage: str = "Running",
        unit: str = "items",
        eta_seconds: float | None = None,
        failures: int = 0,
        detail: str = "",
    ) -> None:
        """``eta_seconds=None`` estimates it from the rate observed across calls.
        ``total=None`` keeps the line indeterminate and drops the ETA: a streamed total is
        only a floor, so a percentage would be invented. ``detail`` follows the ETA."""
        self._set_running(True)
        parts = []
        if total:
            self.progress.setRange(0, int(total))
            self.progress.setValue(min(done, int(total)))
            headline = f"{stage} — {format_count(done)} / {format_count(total)} {unit}"
            if eta_seconds is None:
                eta_seconds = self._estimate_eta(done, int(total))
            parts.append("Estimating time…" if eta_seconds is None else format_eta(eta_seconds))
        else:
            self.progress.setRange(0, 0)
            headline = f"{stage} — {format_count(done)} {unit}"
        if detail:
            parts.append(detail)
        self._show(headline, " · ".join(parts), failures)

    def _estimate_eta(self, done: int, total: int) -> float | None:
        # ponytail: average rate since the first progress call; a sliding window if runs
        # change pace a lot (warm-up, mixed molecule sizes).
        now = _clock()
        if self._rate_origin is None or done < self._rate_origin[1]:
            self._rate_origin = (now, done)
            return None
        since, base = self._rate_origin
        if done <= base or now <= since:
            return None
        return (total - done) * (now - since) / (done - base)

    def finish(self, headline: str, detail: str = "", *, failures: int = 0) -> None:
        """Back to idle showing the outcome (done, failed, cancelled) until the next summary."""
        self._set_running(False)
        self._show(headline, detail, failures)

    def _show(self, headline: str, detail: str, failures: int = 0) -> None:
        self.headline.setText(headline)
        parts = [html.escape(detail)] if detail else []
        if failures:
            parts.append(f'{format_count(failures)} failed · <a href="details">details</a>')
        self.detail.setText(" · ".join(parts))

    def _set_running(self, running: bool) -> None:
        if running == self._running:
            return
        self._running = running
        if running:
            self._actions_box.setMinimumWidth(self._actions_box.sizeHint().width())
            # Only what is visible now: an action the host hid stays hidden afterwards.
            self._restore = [widget for widget in self._run_actions if not widget.isHidden()]
            for widget in self._restore:
                widget.hide()
            self.cancel_button.setEnabled(True)
        else:
            for widget in self._restore:
                widget.show()
            self._restore = []
            self._rate_origin = None
            self._actions_box.setMinimumWidth(0)
        self.cancel_button.setVisible(running)
        self.progress.setVisible(running)
        self._rule.setVisible(not running)
        self.busy_changed.emit(running)

    def _on_cancel(self) -> None:
        self.cancel_button.setEnabled(False)  # one request; the host answers with finish()
        self.cancel_requested.emit()


class ToolPanel(QWidget):
    """Frame for a configure-then-run tool; see the module docstring.

    ``scrollable=False`` for tools whose body is mostly a table that scrolls itself.
    """

    def __init__(self, parent: QWidget | None = None, *, scrollable: bool = True) -> None:
        super().__init__(parent)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)
        self._top_bar: ContentBar | None = None
        self._action_bar: ActionBar | None = None
        self._advanced: ToolSection | None = None

        self.content = QWidget(self)
        self.body_layout = QVBoxLayout(self.content)
        self.body_layout.setContentsMargins(12, 12, 12, 12)
        self.body_layout.setSpacing(14)
        self.body_layout.addStretch(1)  # sections keep their height instead of spreading out
        self._has_tail = True
        if scrollable:
            scroll = QScrollArea(self)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setWidget(self.content)
            self._outer.addWidget(scroll, 1)
        else:
            self._outer.addWidget(self.content, 1)

    @property
    def top_bar(self) -> ContentBar:
        if self._top_bar is None:
            self._top_bar = ContentBar(Qt.Edge.BottomEdge, self)
            self._outer.insertWidget(0, self._top_bar)
        return self._top_bar

    @property
    def action_bar(self) -> ActionBar:
        if self._action_bar is None:
            self._action_bar = ActionBar(self)
            self._action_bar.busy_changed.connect(self._set_busy)
            self._outer.addWidget(self._action_bar)
        return self._action_bar

    @property
    def advanced(self) -> ToolSection:
        """Collapsed section kept last: seed, threads, batch size, executor."""
        if self._advanced is None:
            self._advanced = ToolSection("Advanced", collapsible=True, parent=self.content)
            self._insert(self._advanced, 0)
        return self._advanced

    def add_section(self, title: str, **options) -> ToolSection:
        """Options as in ``ToolSection``; inserted after the previous ones, before Advanced."""
        section = ToolSection(title, parent=self.content, **options)
        self._insert(section, 0)
        return section

    def add_widget(self, widget: QWidget, stretch: int = 0) -> QWidget:
        """A free widget in the body; ``stretch > 0`` lets it take the spare height (tables)."""
        if stretch and self._has_tail:
            self.body_layout.takeAt(self.body_layout.count() - 1)
            self._has_tail = False
        self._insert(widget, stretch)
        return widget

    def _insert(self, widget: QWidget, stretch: int) -> None:
        index = self.body_layout.count() - int(self._has_tail)
        if self._advanced is not None and widget is not self._advanced:
            index -= 1
        self.body_layout.insertWidget(index, widget, stretch)

    def _set_busy(self, busy: bool) -> None:
        # Settings are locked while a run uses them; the action bar stays live for Cancel.
        self.content.setEnabled(not busy)
        if self._top_bar is not None:
            self._top_bar.setEnabled(not busy)
