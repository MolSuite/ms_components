"""ChipsSelect: typed values become chips only when editable; chips reorder."""
from PySide6.QtWidgets import QApplication

from ms_components.chips import ChipsSelect


def test_typing_adds_a_chip_only_when_editable_and_chips_reorder():
    QApplication.instance() or QApplication(["chips-test"])
    chips = ChipsSelect(editable=True, reorderable=True, normalize=lambda text: text.strip().upper())
    chips.set_items(["ZN", "FE"], selected=["ZN", "FE"])
    chips._combo.lineEdit().setText(" mn ")
    chips._combo.lineEdit().returnPressed.emit()
    assert chips.selected_items() == ["ZN", "FE", "MN"]
    chips.move_item("MN", 0)
    assert chips.selected_items() == ["MN", "ZN", "FE"]
    assert not ChipsSelect()._combo.isEditable()  # a closed set (chains, ligands): nothing typed in


def _dialog_with_default_button(chips):
    """A dialog the way hosts build one: an Import button that Return activates by default."""
    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    layout.addWidget(chips)
    buttons = QDialogButtonBox(dialog)
    buttons.addButton("Import", QDialogButtonBox.ButtonRole.AcceptRole)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)
    return dialog


def test_enter_in_the_typed_field_adds_a_chip_and_does_not_submit_the_dialog():
    """Enter means "add this chip" in the field, never "accept the dialog around it".

    QLineEdit ignores Return after emitting returnPressed, so the key used to travel on to the
    dialog and click its default button: typing a metal code and pressing Enter submitted the
    whole receptor import before the user had finished choosing options.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog

    app = QApplication.instance() or QApplication(["chips-test"])
    chips = ChipsSelect(editable=True, normalize=lambda text: text.strip().upper())
    chips.set_items(["ZN"], selected=["ZN"])
    dialog = _dialog_with_default_button(chips)
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog.show()
    field = chips._combo.lineEdit()
    field.setFocus()
    app.processEvents()

    QTest.keyClicks(field, "cd")
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert chips.selected_items() == ["ZN", "CD"]
    QTest.keyClicks(field, "mn")
    QTest.keyClick(field, Qt.Key.Key_Enter)  # the keypad Enter, too
    assert chips.selected_items() == ["ZN", "CD", "MN"]
    assert not accepted and dialog.isVisible() and dialog.result() != QDialog.DialogCode.Accepted
    dialog.close()


def test_enter_in_a_closed_set_still_reaches_the_dialog():
    """Only the typed field claims Enter: a closed set (chains) has nothing to type, so Enter
    keeps its usual meaning there."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    app = QApplication.instance() or QApplication(["chips-test"])
    chips = ChipsSelect()
    chips.set_items(["A", "B"], selected=["A"])
    dialog = _dialog_with_default_button(chips)
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog.show()
    chips._combo.setFocus()
    app.processEvents()
    QTest.keyClick(chips._combo, Qt.Key.Key_Return)
    assert accepted
