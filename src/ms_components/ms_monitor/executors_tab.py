"""Operate the executors declared in settings: test, prepare, activate, launch.

Settings say *which* executors exist and with what parameters; this tab is where
they are actually tested, provisioned and started — /etc versus systemctl.

Blocking rule: only the compute backend the app is about to depend on (a local
or hybrid ray head) runs in a modal dialog. Everything external — HPC, a cluster
someone else manages, remote provisioning — runs non-modal so the app stays
usable while it happens.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ms_components.ms_monitor.palette import P
from ms_components.step_dialog import run_steps_dialog
from ms_flow.core.executor.provisioning import (
    Step,
    cluster_address,
    cluster_down_steps,
    cluster_launch_needed,
    cluster_up_steps,
    prepare_steps,
    test_steps,
)


class ExecutorsTab(QWidget):
    def __init__(self, *, bridge=None, parent: QWidget | None = None):
        super().__init__(parent)
        self._bridge = bridge
        self._workers: dict[str, Any] = {}
        self._live: set[str] = set()

        root = QHBoxLayout(self)
        root.setSpacing(12)

        left = QVBoxLayout()
        self._list = QListWidget(self)
        self._list.currentItemChanged.connect(lambda *_: self._sync_buttons())
        left.addWidget(self._list, 1)
        self._reload_button = QPushButton("Reload from settings", self)
        self._reload_button.clicked.connect(self.refresh)
        left.addWidget(self._reload_button)
        root.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(6)
        self._detail = QLabel("Select an executor.", self)
        self._detail.setWordWrap(True)
        self._detail.setAlignment(Qt.AlignTop)
        self._detail.setStyleSheet("color:palette(text); font-size:12px;")
        right.addWidget(self._detail, 1)

        self._buttons: dict[str, QPushButton] = {}
        for key, label, slot in (
            ("test", "Test", self._on_test),
            ("prepare", "Prepare environment", self._on_prepare),
            ("up", "Launch managed cluster", self._on_cluster_up),
            ("activate", "Activate", self._on_activate),
            ("deactivate", "Deactivate", self._on_deactivate),
            ("down", "Stop managed cluster", self._on_cluster_down),
        ):
            button = QPushButton(label, self)
            button.clicked.connect(slot)
            self._buttons[key] = button
            right.addWidget(button)

        self._apply_button = QPushButton("Apply settings to runtime", self)
        self._apply_button.setToolTip("Re-register every enabled executor from the saved settings.")
        self._apply_button.clicked.connect(self._on_apply_settings)
        right.addWidget(self._apply_button)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:palette(placeholder-text); font-size:11px;")
        right.addWidget(self._status)
        root.addLayout(right, 3)

        if bridge is not None:
            self.attach_bridge(bridge)

    # --- data ---------------------------------------------------------------
    def attach_bridge(self, bridge) -> None:
        self._bridge = bridge
        self.refresh()

    @property
    def _molsuite(self):
        return getattr(self._bridge, "molsuite", None)

    def set_live_executors(self, names) -> None:
        self._live = {str(name) for name in names or ()}
        self._repopulate()

    def refresh(self) -> None:
        molsuite = self._molsuite
        settings = getattr(getattr(molsuite, "settings_manager", None), "settings", None)
        self._workers = dict(settings.get_all_workers()) if settings is not None else {}
        self._repopulate()

    def _repopulate(self) -> None:
        selected = self._selected_name()
        self._list.blockSignals(True)
        self._list.clear()
        for name, worker in sorted(self._workers.items()):
            marks = []
            if not getattr(worker, "enabled", True):
                marks.append("disabled")
            marks.append("live" if name in self._live else "not registered")
            item = QListWidgetItem(f"{name}  –  {getattr(worker, 'type', '?')}  ({', '.join(marks)})")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self._list.addItem(item)
        self._list.blockSignals(False)
        if selected is not None:
            for row in range(self._list.count()):
                if self._list.item(row).data(Qt.ItemDataRole.UserRole) == selected:
                    self._list.setCurrentRow(row)
                    break
        elif self._list.count():
            self._list.setCurrentRow(0)
        self._sync_buttons()

    def _selected_name(self) -> str | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _selected(self):
        name = self._selected_name()
        return self._workers.get(name) if name else None

    def _sync_buttons(self) -> None:
        worker = self._selected()
        wtype = str(getattr(worker, "type", "")).lower() if worker is not None else ""
        is_cluster = worker is not None and cluster_launch_needed(worker)
        remote = wtype in ("ray", "hpc")
        for key, button in self._buttons.items():
            button.setEnabled(worker is not None)
        self._buttons["up"].setVisible(is_cluster)
        self._buttons["down"].setVisible(is_cluster)
        self._buttons["prepare"].setEnabled(remote and worker is not None)
        self._detail.setText(self._describe(worker))

    def _describe(self, worker) -> str:
        if worker is None:
            return "Select an executor."
        wtype = str(getattr(worker, "type", "")).lower()
        lines = [f"<b>{getattr(worker, 'name', '')}</b> · {wtype}"]
        if wtype == "ray":
            lines.append(f"mode: {getattr(worker, 'mode', '')}")
            if cluster_launch_needed(worker):
                lines.append(f"head: {getattr(worker, 'head_ip', '') or 'this machine'}")
                lines.append("workers: " + ", ".join(getattr(worker, "worker_ips", []) or []))
                lines.append(f"address once up: {cluster_address(worker)}")
            else:
                lines.append(f"address: {getattr(worker, 'address', '')}")
        elif wtype == "hpc":
            lines.append(f"host: {getattr(worker, 'host', '')} · scheduler: {getattr(worker, 'scheduler', '')}")
        if getattr(worker, "conda_env", ""):
            lines.append(f"conda env: {getattr(worker, 'conda_env')} (created if missing)")
        status = self._backend_status()
        if status:
            lines.append("")
            lines.append(f"compute backend: {status.get('backend', '?')} ({status.get('state', '?')})")
            if status.get("fallback_reason"):
                lines.append(f"<i>{status['fallback_reason']}</i>")
        return "<br>".join(lines)

    def _backend_status(self) -> dict:
        molsuite = self._molsuite
        if molsuite is None:
            return {}
        try:
            return dict(molsuite.compute_backend_status())
        except Exception:
            return {}

    # --- actions ------------------------------------------------------------
    def _run(self, title: str, steps, *, blocking: bool = False) -> None:
        steps = list(steps)
        if not steps:
            self._status.setText("Nothing to do for this executor.")
            return
        run_steps_dialog(self, title, steps, blocking=blocking, on_success=self._after_action)

    def _after_action(self) -> None:
        self._status.setText("Done.")
        self.refresh()

    def _on_test(self) -> None:
        worker = self._selected()
        if worker is not None:
            self._run(f"Test '{worker.name}'", test_steps(worker))

    def _on_prepare(self) -> None:
        worker = self._selected()
        if worker is None:
            return
        steps = prepare_steps(worker)
        if not steps:
            QMessageBox.information(
                self,
                "Prepare environment",
                "Nothing to prepare: this executor has no remote hosts of its own "
                "(local, or a cluster managed elsewhere).",
            )
            return
        self._run(f"Prepare '{worker.name}'", steps)

    def _on_cluster_up(self) -> None:
        worker = self._selected()
        if worker is None:
            return
        # The cluster we are about to run jobs on: block until it is up.
        self._run(
            f"Launch cluster '{worker.name}'",
            [*cluster_up_steps(worker), self._activate_step(worker, cluster_address(worker))],
            blocking=True,
        )

    def _on_cluster_down(self) -> None:
        worker = self._selected()
        molsuite = self._molsuite
        if worker is None or molsuite is None:
            return

        def deactivate() -> str:
            max_workers = int(getattr(molsuite.settings_manager.settings.resources.local, "max_processes", 0) or 0)
            molsuite.activate_compute_backend(
                "loky",
                max_workers=max_workers or None,
                policy="cancel_and_wait",
            )
            return "Ray jobs drained/canceled and MF detached from the cluster."

        self._run(
            f"Stop cluster '{worker.name}'",
            [Step("detach ray backend", call=deactivate, timeout=300), *cluster_down_steps(worker)],
            blocking=True,
        )

    def _on_activate(self) -> None:
        worker = self._selected()
        if worker is None:
            return
        wtype = str(getattr(worker, "type", "")).lower()
        if wtype != "ray":
            self._run(f"Activate '{worker.name}'", [self._register_step(worker)])
            return
        mode = str(getattr(worker, "mode", "external")).lower()
        if cluster_launch_needed(worker):
            QMessageBox.information(
                self,
                "Activate",
                "This is a managed cluster: use “Launch managed cluster” instead.",
            )
            return
        address = str(getattr(worker, "address", "")).strip() if mode != "local" else ""
        # Local head = the backend everything will run on -> blocking dialog.
        self._run(
            f"Activate ray '{worker.name}'",
            [*test_steps(worker), self._activate_step(worker, address)],
            blocking=(mode == "local"),
        )

    def _on_deactivate(self) -> None:
        worker = self._selected()
        molsuite = self._molsuite
        if worker is None or molsuite is None:
            return
        name = str(getattr(worker, "name", ""))
        wtype = str(getattr(worker, "type", "")).lower()

        def call() -> str:
            if wtype == "ray":
                max_workers = int(getattr(molsuite.settings_manager.settings.resources.local, "max_processes", 0) or 0)
                molsuite.activate_compute_backend("loky", max_workers=max_workers or None, policy="cancel_and_wait")
                return "Compute backend switched back to loky."
            molsuite.unregister_executor(name)
            return f"Executor '{name}' unregistered."

        self._run(f"Deactivate '{name}'", [Step(f"deactivate {name}", call=call, timeout=120)])

    def _on_apply_settings(self) -> None:
        molsuite = self._molsuite
        if molsuite is None:
            return

        def call() -> str:
            # Explicit user action off the GUI thread: ray may be activated here.
            result = molsuite.reload_configured_executors(allow_remote_compute=True)
            reason = result.get("fallback_reason") or ""
            names = ", ".join(result.get("executors", []))
            return f"Registered: {names}." + (f" {reason}" if reason else "")

        self._run("Apply settings", [Step("re-register executors", call=call, timeout=120)])

    def _activate_step(self, worker, address: str) -> Step:
        molsuite = self._molsuite
        mode = str(getattr(worker, "mode", "external")).lower()
        cpus = int(getattr(worker, "cpus", 0) or 0)
        shared_fs = getattr(worker, "shared_fs", None)
        gpu_slots_per_device = int(getattr(worker, "gpu_slots_per_device", 1) or 1)

        def call() -> str:
            status = molsuite.activate_compute_backend(
                "ray",
                ray_mode=mode,
                cpus=cpus,
                address=address or None,
                shared_fs=shared_fs,
                gpu_slots_per_device=gpu_slots_per_device,
                policy="cancel_and_wait",
            )
            return f"Ray backend: {status.get('state', 'registered')} ({address or mode})"

        return Step("activate ray backend", call=call, timeout=300)

    def _register_step(self, worker) -> Step:
        molsuite = self._molsuite
        name = str(getattr(worker, "name", ""))
        wtype = str(getattr(worker, "type", "")).lower()

        def call() -> str:
            if wtype == "hpc":
                molsuite.register_hpc_executor(
                    name=name,
                    shared_fs=bool(getattr(worker, "shared_fs", False)),
                    submit_command=getattr(worker, "submit_command", None),
                    poll_command=getattr(worker, "poll_command", None),
                    cancel_command=getattr(worker, "cancel_command", None),
                    poll_interval_s=float(getattr(worker, "poll_interval_s", 2.0)),
                    command_env=getattr(worker, "command_env", None),
                    python_executable=getattr(worker, "python_executable", None),
                )
                return f"HPC executor '{name}' registered."
            molsuite.reload_configured_executors()
            return f"Local executors re-registered from settings ('{name}' included)."

        return Step(f"register {name}", call=call, timeout=120)


__all__ = ["ExecutorsTab"]
