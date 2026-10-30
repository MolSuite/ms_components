import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSpinBox, QTableWidget, QWidget  # noqa: E402

from ms_components import tool_panel  # noqa: E402
from ms_components.tool_panel import (  # noqa: E402
    ContentBar,
    ToolPanel,
    ToolSection,
    format_count,
    format_eta,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication(["tool-panel-test"])


def _body_widgets(panel: ToolPanel) -> list:
    layout = panel.body_layout
    return [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget()]


def test_styles_live_in_base_qss_not_inline():
    _app()
    from ms_components.theme import base_qss

    panel = ToolPanel()
    panel.add_section("Other")
    panel.advanced  # the collapsible section with the toggle
    panel.action_bar
    assert all(not widget.styleSheet() for widget in panel.findChildren(QWidget))
    qss = base_qss()
    assert f"#{tool_panel.PROGRESS_NAME}" in qss and f"#{tool_panel.SECTION_TOGGLE_NAME}" in qss
    assert panel.action_bar.progress.objectName() == tool_panel.PROGRESS_NAME


def test_formatters():
    assert format_count(12480) == "12 480"
    assert format_eta(None) == ""
    assert format_eta(30) == "< 1 min left"
    assert format_eta(180) == "≈ 3 min left"
    assert format_eta(3599) == "≈ 1 h left"
    assert format_eta(5400) == "≈ 1 h 30 min left"


def test_bars_exist_only_once_used():
    _app()
    panel = ToolPanel()
    assert panel.findChild(ContentBar) is None

    panel.top_bar.add_label("Apply to")
    bar = panel.action_bar
    assert panel.top_bar is panel.top_bar
    assert panel.layout().indexOf(panel.top_bar) == 0
    assert panel.layout().indexOf(bar) == panel.layout().count() - 1


def test_sections_keep_order_and_advanced_stays_last():
    _app()
    panel = ToolPanel()
    first = panel.add_section("Protonation")
    advanced = panel.advanced
    second = panel.add_section("Minimization")

    assert _body_widgets(panel) == [first, second, advanced]
    assert not advanced.isExpanded() and advanced.body.isHidden()
    advanced.setExpanded(True)
    assert not advanced.body.isHidden()


def test_stretched_widget_replaces_the_trailing_stretch():
    _app()
    panel = ToolPanel(scrollable=False)
    panel.add_section("Source")
    layout = panel.body_layout
    assert layout.itemAt(layout.count() - 1).spacerItem() is not None

    table = panel.add_widget(QTableWidget(), stretch=1)
    assert all(layout.itemAt(i).spacerItem() is None for i in range(layout.count()))
    assert layout.stretch(layout.indexOf(table)) == 1


def test_checkable_section_disables_or_collapses_its_body():
    _app()
    section = ToolSection("Protonation", checkable=True)
    seen = []
    section.toggled.connect(seen.append)
    section.setChecked(False)
    assert seen == [False]
    assert not section.body.isEnabled() and not section.body.isHidden()

    flexible = ToolSection("Flexible residues", checkable=True, checked=False, collapse_when_unchecked=True)
    assert flexible.body.isHidden()
    flexible.setChecked(True)
    assert not flexible.body.isHidden() and flexible.body.isEnabled()

    plain = ToolSection("Engines")
    assert plain.isChecked() and not plain.body.isHidden()


def test_run_cycle_swaps_actions_locks_settings_and_restores():
    app = _app()
    panel = ToolPanel()
    spin = QSpinBox()
    panel.add_section("Minimization").add_row("Max iterations", spin)
    scope = panel.top_bar.add_widget(QLabel("scope"))
    bar = panel.action_bar
    save = bar.add_action(QPushButton("Save to workflow"))
    run = bar.add_action(QPushButton("Run"))
    hidden_by_host = bar.add_action(QPushButton("Unavailable"))
    hidden_by_host.hide()
    results = bar.add_action(QPushButton("Open Results"), hide_while_running=False)
    bar.set_summary("12 480 molecules", "Estimated ≈ 6 min on 8 threads")
    panel.resize(700, 400)
    panel.show()
    app.processEvents()
    idle_width = run.parentWidget().width()

    bar.set_progress(4820, 12480, stage="Minimizing", unit="molecules", eta_seconds=180, failures=12)
    app.processEvents()
    assert bar.is_running
    assert run.isHidden() and save.isHidden() and not bar.cancel_button.isHidden()
    assert not results.isHidden()
    assert not spin.isEnabled() and not scope.isEnabled()
    assert bar.headline.text() == "Minimizing - 4 820 / 12 480 molecules"
    assert "≈ 3 min left" in bar.detail.text() and "12 failed" in bar.detail.text()
    assert (bar.progress.value(), bar.progress.maximum()) == (4820, 12480)
    assert run.parentWidget().width() == idle_width  # nothing on the left jumps

    bar.finish("12 468 molecules ready", failures=12)
    app.processEvents()
    assert not bar.is_running
    assert not run.isHidden() and not save.isHidden() and hidden_by_host.isHidden()
    assert bar.cancel_button.isHidden() and bar.progress.isHidden()
    assert spin.isEnabled() and scope.isEnabled()
    panel.close()


def test_eta_comes_from_the_observed_rate_and_restarts_after_a_requeue(monkeypatch):
    _app()
    panel = ToolPanel()
    bar = panel.action_bar
    now = [100.0]
    monkeypatch.setattr(tool_panel, "_clock", lambda: now[0])

    bar.set_progress(0, 10, unit="batches", detail="3 running")
    assert bar.detail.text() == "Estimating time… · 3 running"
    now[0] = 160.0
    bar.set_progress(2, 10, unit="batches", detail="3 running")
    assert bar.detail.text() == "≈ 4 min left · 3 running"  # 2 per minute, 8 to go

    bar.start("Queued")
    now[0] = 1000.0
    bar.set_progress(3, 10)
    assert bar.detail.text() == "Estimating time…"


def test_unknown_total_is_indeterminate_and_signals_fire():
    _app()
    panel = ToolPanel()  # keep the owner alive: the bar is its child
    bar = panel.action_bar
    cancelled, details = [], []
    bar.cancel_requested.connect(lambda: cancelled.append(True))
    bar.details_requested.connect(lambda: details.append(True))

    bar.set_progress(4820, None, stage="Importing", unit="molecules", eta_seconds=60, failures=3)
    assert bar.progress.maximum() == 0
    assert bar.headline.text() == "Importing - 4 820 molecules"
    assert "left" not in bar.detail.text()

    bar.cancel_button.click()
    assert cancelled == [True] and not bar.cancel_button.isEnabled()
    bar.detail.linkActivated.emit("details")
    assert details == [True]
