from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class MetricCard(QFrame):
    """Compact KPI tile: title, big value, optional muted subtitle and a colored
    left accent bar. `set_value` stays backward compatible (value only)."""

    def __init__(
        self,
        title: str,
        value: str = "-",
        *,
        subtitle: str = "",
        accent: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        # QSS resolves palette(...) live, so the default accent follows the theme.
        self._accent = accent or "palette(highlight)"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self._title = QLabel(title, self)
        self._title.setObjectName("metricTitle")
        self._value = QLabel(value, self)
        self._value.setObjectName("metricValue")
        self._subtitle = QLabel(subtitle, self)
        self._subtitle.setObjectName("metricSub")
        self._subtitle.setVisible(bool(subtitle))

        layout.addWidget(self._title)
        layout.addWidget(self._value)
        layout.addWidget(self._subtitle)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#metricCard {{
                background: palette(base);
                border: 1px solid palette(mid);
                border-left: 3px solid {self._accent};
                border-radius: 10px;
            }}
            QLabel#metricTitle {{
                color: palette(placeholder-text);
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }}
            QLabel#metricValue {{
                color: palette(text);
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#metricSub {{
                color: palette(placeholder-text);
                font-size: 10px;
            }}
            """
        )

    def set_value(self, value: str, subtitle: str | None = None, *, accent: str | None = None) -> None:
        self._value.setText(value)
        if subtitle is not None:
            self._subtitle.setText(subtitle)
            self._subtitle.setVisible(bool(subtitle))
        if accent is not None and accent != self._accent:
            self._accent = accent
            self._apply_style()
