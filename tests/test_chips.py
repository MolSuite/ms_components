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
