"""The Settings pages of hosts and executors and the quick panel, on a real workspace whose
Ray runs nothing."""
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from ms_components.ms_executors import ExecutorsPanel, KeptPage, _value


class _Ray:
    capacity, uses_tokens = 1, False

    def __init__(self, *said, **init):
        pass

    def bind(self, on_done):
        pass

    def shutdown(self):
        pass


def _until(check, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not check():
        QApplication.processEvents()
        time.sleep(0.01)
    return check()


def test_hosts_and_executors_are_kept_and_started_from_the_ui(tmp_path, monkeypatch):
    from ms_flow import engine as engines
    from ms_flow import ray_hosts
    from ms_flow.api import Workspace

    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("MOLSUITE_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(ray_hosts, "RayOverHosts", _Ray)
    monkeypatch.setattr(engines, "RayExecutor", _Ray)
    monkeypatch.setattr(QMessageBox, "question", lambda *asked: QMessageBox.StandardButton.Yes)
    ms = Workspace(app_id="ui")
    try:
        hosts, executors = KeptPage(ms, "hosts"), KeptPage(ms, "executors")

        assert not hosts._editors["address"].isEnabled() and not hosts.remove_button.isEnabled()  # `local`
        hosts.new_button.click()
        hosts.name.setText("laptop")
        hosts.save_button.click()
        assert "no address" in hosts.said.text() and "laptop" not in ms.settings_manager.settings.hosts
        hosts._editors["address"].setText("192.168.1.2")
        hosts._editors["env"].setText("/env")
        hosts._editors["cpus"].setValue(-2)
        hosts._editors["tools"].setPlainText("vina = /opt/vina")
        hosts.save_button.click()
        laptop = ms.settings_manager.settings.hosts["laptop"]
        assert (laptop.address, laptop.cpus, laptop.tools) == ("192.168.1.2", -2, {"vina": "/opt/vina"})
        assert hosts.names.currentItem().text() == "laptop" and hosts.name.isReadOnly()

        executors.reload()  # what showing it does
        assert not executors._editors["kind"].isEnabled()  # `local` is the pool, and stays so
        assert executors._editors["scheduler"].isHidden() and not executors._editors["on_login_node"].isHidden()
        executors.new_button.click()
        kind, ticks = executors._editors["kind"], executors._editors["hosts"]
        assert [kind.itemData(i) for i in range(kind.count())] == ["ray", "queue"]
        assert executors._editors["scheduler"].isHidden() and executors._editors["on_login_node"].isHidden()
        for row in range(ticks.count()):
            ticks.item(row).setCheckState(Qt.CheckState.Checked)
        kind.setCurrentIndex(kind.findData("queue"))
        assert not executors._editors["scheduler"].isHidden()
        # A queue has one machine, its login node: the ticks of a Ray do not stay, and one tick takes the other's place.
        assert executors._form.labelForField(ticks).text() == "Login node" and _value(ticks) == ["local"]
        ticks.item(1).setCheckState(Qt.CheckState.Checked)
        assert _value(ticks) == ["laptop"]
        kind.setCurrentIndex(kind.findData("ray"))
        assert executors._form.labelForField(ticks).text() == "Hosts"
        executors.name.setText("lab")
        for row in range(ticks.count()):
            ticks.item(row).setCheckState(Qt.CheckState.Checked)
        executors.save_button.click()
        lab = ms.settings_manager.settings.executors["lab"]
        assert (lab.kind, lab.hosts) == ("ray", ["local", "laptop"]) and "is kept" in executors.said.text()

        hosts.reload(select="laptop")
        hosts.remove_button.click()
        assert "is a host of lab" in hosts.said.text()  # refused by the workspace, and said

        panel = ExecutorsPanel(ms)
        assert panel.states["lab"].text() == "Off" and panel.defaults["local"].isChecked()
        panel.defaults["lab"].click()
        assert ms.settings_manager.settings.general.default_executor == "lab"
        ms.create_or_open_project(name="one", folder=tmp_path / "one", description="", activate=True)
        panel.buttons["lab"].click()
        assert _until(lambda: panel.states["lab"].text() == "On")
        assert panel.buttons["lab"].text() == "Deactivate"
        assert "`local` works for `lab`" in panel.states["local"].text() and not panel.buttons["local"].isEnabled()
        executors.reload(select="lab")
        executors.save_button.click()
        assert "in use by `lab`" in executors.said.text()
        panel.buttons["lab"].click()
        assert _until(lambda: panel.states["lab"].text() == "Off" and panel.states["local"].text() == "On")

        def unprepared(address, busy, on_line):
            on_line(f"looking for {address}")
            raise OSError(f"{address} is not reached")

        ms.host_env = unprepared
        ms.save_host("laptop", address="192.168.1.2")  # no environment named: the app is asked, and fails
        panel.buttons["lab"].click()
        assert _until(lambda: "lab: 192.168.1.2 is not reached" in panel.said.toPlainText())
        assert "looking for 192.168.1.2" in panel.said.toPlainText() and panel.states["lab"].text() == "Off"

        executors.reload(select="lab")
        executors.remove_button.click()
        assert "lab" not in ms.settings_manager.settings.executors
        panel.refresh()
        assert set(panel.buttons) >= {"local"} and "lab" not in [row["name"] for row in ms.executors()]
    finally:
        ms.shutdown()
        app.processEvents()
