import pytest
from PySide6.QtWidgets import QApplication, QLabel

from ms_components.ms_stepper import Orientation, QStepper


@pytest.mark.parametrize("orientation", [Orientation.HORIZONTAL, Orientation.VERTICAL])
def test_a_new_step_leaves_the_others_where_they_are(orientation):
    QApplication.instance() or QApplication([])
    stepper = QStepper(orientation=orientation, linear=False)
    first = stepper.add_step("One")
    first.add_widget(QLabel("page one"))
    parent = first.parentWidget()
    second, third = stepper.add_step("Two"), stepper.add_step("Three")

    assert first.parentWidget() is parent  # not taken out and put back
    assert stepper.count() == 3 and stepper.current_index == 0
    assert len(stepper._header_items or stepper._rails) == 3
    stepper.go_to(third)
    assert stepper.current_step() is third
    if orientation == Orientation.HORIZONTAL:
        assert stepper._stack.currentWidget() is third and stepper._stack.count() == 3
    else:
        assert third.isVisibleTo(stepper) and not second.isVisibleTo(stepper)
