"""A window-local spotlight: informative steps block input, interactive steps open a hole."""
from __future__ import annotations

from math import ceil

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTextBrowser,
    QVBoxLayout, QWidget,
)
from PySide6.QtGui import QRegion

from .models import TutorialStep


class TutorialOverlay(QWidget):
    next_requested = Signal()
    back_requested = Signal()
    exit_requested = Signal()

    def __init__(self, host: QWidget, *, dim_background: bool = True):
        super().__init__(host)
        self.dim_background = dim_background
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hole = QRect()
        self.step: TutorialStep | None = None
        self._size_key = None
        self._place_key = None
        self.panel = QFrame(self)
        self.panel.setObjectName("TutorialCallout")
        self.panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.panel.setAutoFillBackground(True)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        self.counter = QLabel()
        self.title = QLabel()
        for label in (self.counter, self.title):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
        font = self.title.font()
        font.setPointSizeF(font.pointSizeF() * 1.25)
        font.setBold(True)
        self.title.setFont(font)
        self.body = QTextBrowser()
        self.body.setObjectName("TutorialText")
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        self.body.setOpenExternalLinks(False)
        self.body.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for widget in (self.counter, self.title, self.body):
            layout.addWidget(widget)
        actions = QHBoxLayout()
        self.exit_button = QPushButton(self.tr("Exit · Esc"))
        self.back_button = QPushButton(self.tr("Back"))
        self.next_button = QPushButton(self.tr("Next"))
        for button in (self.exit_button, self.back_button, self.next_button):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.exit_button.clicked.connect(self.exit_requested)
        self.back_button.clicked.connect(self.back_requested)
        self.next_button.clicked.connect(self.next_requested)

    def set_step(self, tutorial_title: str, step: TutorialStep, index: int, count: int):
        self.step = step
        self._size_key = None
        self._place_key = None
        self.counter.setText(f"{tutorial_title} · {index + 1} / {count}")
        self.title.setText(step.title)
        self.body.setPlainText(step.text)
        self.back_button.setEnabled(index > 0)
        self.next_button.setText(self.tr("Finish") if index == count - 1 else self.tr("Next"))
        self.setAccessibleName(tutorial_title)
        self.setAccessibleDescription(f"{step.title}. {step.text}")

    def set_text(self, text: str):
        """Update instructions without resetting their layout or scroll position each tick."""
        if self.body.toPlainText() != text:
            self.body.setPlainText(text)
            self._size_key = None
            self._place_key = None
            self.setAccessibleDescription(f"{self.step.title}. {text}")

    def reposition(self, target: QWidget, *, interactive: bool, rect: QRect | None = None):
        host = self.parentWidget()
        self.setGeometry(host.rect())
        target_rect = target.rect() if rect is None else target.rect().intersected(rect)
        top_left = self.mapFromGlobal(target.mapToGlobal(target_rect.topLeft()))
        self.hole = QRect(top_left, target_rect.size()).intersected(self.rect())
        # Clip to ancestor viewports (for targets inside a scroll area).
        ancestor = target.parentWidget()
        while ancestor is not None and ancestor is not host:
            origin = self.mapFromGlobal(ancestor.mapToGlobal(QPoint()))
            self.hole &= QRect(origin, ancestor.size())
            ancestor = ancestor.parentWidget()
        if self.hole.isEmpty():
            self.hide()
            return

        width = min(420, max(1, self.width() - 24))
        self.panel.ensurePolished()
        self.body.ensurePolished()
        panel_margins = self.panel.contentsMargins()
        body_margins = self.body.contentsMargins()
        size_key = (width, self.height(), self.body.font().key(), panel_margins, body_margins)
        if size_key != self._size_key:
            self.panel.setFixedWidth(width)
            margins = self.panel.layout().contentsMargins()
            text_width = (width - panel_margins.left() - panel_margins.right()
                          - margins.left() - margins.right()
                          - body_margins.left() - body_margins.right())
            # Measuring the live document fights QTextBrowser's viewport layout and scrollbar.
            measurement = self.body.document().clone()
            measurement.setDefaultFont(self.body.font())
            measurement.setTextWidth(max(1, text_width))
            text_height = ceil(measurement.size().height()) + body_margins.top() + body_margins.bottom() + 2
            self.body.setFixedHeight(min(max(40, text_height), max(40, self.height() // 3)))
            self.panel.adjustSize()
            self._size_key = size_key
        size = self.panel.size()
        candidates = [
            QPoint(self.hole.right() + 16, self.hole.top()),
            QPoint(self.hole.left() - size.width() - 16, self.hole.top()),
            QPoint(self.hole.left(), self.hole.bottom() + 16),
            QPoint(self.hole.left(), self.hole.top() - size.height() - 16),
        ]
        positions = [QPoint(max(12, min(p.x(), self.width() - size.width() - 12)),
                            max(12, min(p.y(), self.height() - size.height() - 12)))
                     for p in candidates]
        position = next((p for p in positions if not QRect(p, size).intersects(self.hole)),
                        positions[-1])
        # The tracker calls this every tick: an unchanged layout must not repaint the window.
        # ponytail: a sibling raised over a still overlay stays on top until the target moves.
        place_key = (QRect(self.hole), position, interactive, self.size())
        if place_key == self._place_key and self.isVisible():
            return
        self._place_key = place_key
        self.panel.move(position)
        region = QRegion(self.rect())
        if interactive:
            region = region.subtracted(QRegion(self.hole)).united(QRegion(self.panel.geometry()))
        self.setMask(region)
        self.show()
        self.raise_()
        self.update()

    def focus_guide(self):
        (self.next_button if self.next_button.isEnabled() else self.exit_button).setFocus()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.dim_background:
            shade = self.palette().color(QPalette.ColorRole.Shadow)
            shade.setAlpha(170)
            path = QPainterPath()
            path.addRect(QRectF(self.rect()))
            opening = QPainterPath()
            opening.addRect(QRectF(self.hole))
            painter.fillPath(path.subtracted(opening), shade)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Highlight), 3))
        painter.drawRoundedRect(QRectF(self.hole.adjusted(-3, -3, 3, 3)), 6, 6)
