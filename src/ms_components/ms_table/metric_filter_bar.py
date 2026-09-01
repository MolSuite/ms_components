"""Additive numeric filter bar, rendered as chips.

What you see is only the state: the active chips and a `+`. The `+` opens a dialog (field,
operator, value); accepting it adds the chip and emits `changed` — no loose combos in the bar
competing with the chips for attention, and no `Apply`: what is applied is what you read.

Chips are keyed by `(field, operator)`, so `Score ≥ -9.5` and `Score ≤ -9` coexist: that is a
**range**, and several fields accumulate.

The widget knows nothing about SQL or sessions: `conditions()` returns `[(field, op, value)]` and
the caller decides what to do with it (in AMDock they become `AND` clauses over the column or over
a JSON of metrics). That decoupling is what makes it reusable; the `FilterPanel` in this same
package is a different thing: it filters a `TableConfig` by equality/ILIKE and cannot express
ranges.

No styles of its own: `QFrame.StyledPanel` picks up the app theme's colours.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

#: (key, symbol) — the two that make sense on a number. The key is what travels in
#: `conditions()`; translating it to `>=` / `<=` is up to the consumer.
OPERATORS = (("gte", "≥"), ("lte", "≤"))

Condition = tuple[str, str, float]


class _ConditionDialog(QDialog):
    """Field + operator + value. Modal and tiny: open it, accept it, forget it."""

    def __init__(
        self,
        fields: Sequence[tuple[str, str]],
        parent: QWidget | None = None,
        *,
        decimals: int,
        value: float,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add filter")
        form = QFormLayout(self)
        self.field_combo = QComboBox(self)
        for key, label in fields:
            self.field_combo.addItem(label, key)
        self.op_combo = QComboBox(self)
        for key, label in OPERATORS:
            self.op_combo.addItem(label, key)
        self.value_spin = QDoubleSpinBox(self)
        self.value_spin.setRange(-1e6, 1e6)
        self.value_spin.setDecimals(decimals)
        self.value_spin.setValue(value)
        form.addRow("Field", self.field_combo)
        form.addRow("Operator", self.op_combo)
        form.addRow("Value", self.value_spin)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def condition(self) -> Condition:
        return (
            str(self.field_combo.currentData() or ""),
            str(self.op_combo.currentData() or ""),
            float(self.value_spin.value()),
        )


class _Chip(QFrame):
    """One active condition. `removed` carries its `(field, operator)` key."""

    removed = Signal(str, str)

    def __init__(self, field: str, op: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MetricChip")
        self.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(2)
        label = QLabel(text, self)
        font = label.font()  # one point smaller: a chip is state, not a headline
        font.setPointSizeF(max(6.0, font.pointSizeF() - 1))
        label.setFont(font)
        layout.addWidget(label)
        close = QToolButton(self)
        close.setText("×")
        close.setAutoRaise(True)
        close.setFocusPolicy(Qt.NoFocus)
        close.setFixedSize(14, 14)
        close.setToolTip("Remove this filter")
        close.clicked.connect(lambda: self.removed.emit(field, op))
        layout.addWidget(close)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)  # a chip is as wide as its text, no more


class MetricFilterBar(QWidget):
    """Chips over numeric fields, plus a `+` that opens the condition dialog.

    `fields` are `(key, label)` pairs: the key is what shows up in `conditions()`.
    """

    changed = Signal()

    def __init__(
        self,
        fields: Sequence[tuple[str, str]],
        parent: QWidget | None = None,
        *,
        decimals: int = 3,
        default_value: float = 0.0,
        empty_text: str = "No filters — everything is shown.",
    ):
        super().__init__(parent)
        self._fields = tuple(fields)
        self._labels = {key: label for key, label in fields}
        self._decimals = decimals
        self._default_value = default_value
        self._conditions: dict[tuple[str, str], float] = {}
        self._chips: dict[tuple[str, str], _Chip] = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.add_button = QToolButton(self)
        self.add_button.setText("+")
        self.add_button.setToolTip("Add a filter")
        self.add_button.clicked.connect(self.open_dialog)
        row.addWidget(self.add_button)
        self._empty = QLabel(empty_text, self)
        self._empty.setEnabled(False)
        row.addWidget(self._empty)
        row.addStretch(1)
        self._row = row

    # --- Public API --------------------------------------------------------
    def conditions(self) -> list[Condition]:
        return [(field, op, value) for (field, op), value in self._conditions.items()]

    def open_dialog(self) -> None:
        dialog = _ConditionDialog(
            self._fields, self, decimals=self._decimals, value=self._default_value
        )
        if dialog.exec() == QDialog.Accepted:
            self.add_condition(*dialog.condition())

    def add_condition(self, field: str, op: str, value: float, *, notify: bool = True) -> None:
        """Add (or replace) a condition: the same field+operator is an edit, not another chip."""
        if field not in self._labels or op not in dict(OPERATORS):
            return
        self._drop((field, op))
        self._conditions[(field, op)] = float(value)
        symbol = dict(OPERATORS)[op]
        chip = _Chip(field, op, f"{self._labels[field]} {symbol} {float(value):g}", self)
        chip.removed.connect(self._on_removed)
        self._chips[(field, op)] = chip
        self._row.insertWidget(self._row.count() - 1, chip)  # before the stretch
        self._empty.setVisible(False)
        if notify:
            self.changed.emit()

    def set_conditions(self, conditions: Iterable[Condition]) -> None:
        """Whole state at once (restoring a saved view): a single signal."""
        for key in list(self._chips):
            self._drop(key)
        for field, op, value in conditions:
            self.add_condition(field, op, value, notify=False)
        self.changed.emit()

    def clear(self) -> None:
        if not self._conditions:
            return
        for key in list(self._chips):
            self._drop(key)
        self.changed.emit()

    # --- internos -----------------------------------------------------------
    def _on_removed(self, field: str, op: str) -> None:
        self._drop((field, op))
        self.changed.emit()

    def _drop(self, key: tuple[str, str]) -> None:
        self._conditions.pop(key, None)
        chip = self._chips.pop(key, None)
        if chip is not None:
            self._row.removeWidget(chip)
            chip.deleteLater()
        self._empty.setVisible(not self._chips)


if __name__ == "__main__":  # minimal check: range, edit, removal and the dialog
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    bar = MetricFilterBar([("score", "Score"), ("le", "LE")])
    seen = []
    bar.changed.connect(lambda: seen.append(len(bar.conditions())))

    bar.add_condition("score", "lte", -9.0)
    bar.add_condition("score", "gte", -9.5)  # different operator = range, not a replacement
    assert sorted(bar.conditions()) == [("score", "gte", -9.5), ("score", "lte", -9.0)]
    bar.add_condition("score", "lte", -8.0)  # same field+operator = an edit
    assert ("score", "lte", -8.0) in bar.conditions() and len(bar.conditions()) == 2
    bar.add_condition("nope", "lte", 1.0)  # unknown field: ignored
    assert len(bar.conditions()) == 2
    bar._chips[("score", "gte")].removed.emit("score", "gte")
    assert bar.conditions() == [("score", "lte", -8.0)]
    bar.set_conditions([("le", "gte", 0.3)])
    assert bar.conditions() == [("le", "gte", 0.3)]
    bar.clear()
    assert bar.conditions() == [] and seen == [1, 2, 2, 1, 1, 0]

    dialog = _ConditionDialog([("score", "Score")], decimals=3, value=-8.5)
    assert dialog.condition() == ("score", "gte", -8.5)
    print("ok")
