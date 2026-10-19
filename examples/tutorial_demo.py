"""Run in MSDD_312: PYTHONPATH=src python examples/tutorial_demo.py."""
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from ms_components.ms_tutorial import (
    Tutorial, TutorialController, TutorialEvent, TutorialStep, TutorialTarget, load_tutorial,
)
from ms_components.theme import apply_theme


class DemoWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ms_tutorial · Python + TOML")
        self.resize(900, 640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(18)
        layout.addWidget(QLabel("Tutoriales independientes de la aplicación"))
        self.load_button = QPushButton("Cargar ejemplo")
        self.status = QLabel("Sin datos de muestra")
        layout.addWidget(self.load_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.status)
        layout.addStretch()
        self.info_button = QPushButton("Recorrido informativo · Python")
        self.interactive_button = QPushButton("Recorrido interactivo · TOML")
        layout.addWidget(self.info_button)
        layout.addWidget(self.interactive_button)
        self.details = QDialog(self)
        self.details.setWindowTitle("Detalles")
        self.details.resize(600, 420)
        details_layout = QVBoxLayout(self.details)
        self.details_text = QLabel("Este panel pertenece a otro diálogo.")
        details_layout.addWidget(self.details_text, alignment=Qt.AlignmentFlag.AlignTop)
        details_layout.addStretch()

        # Existing application behavior: no tutorial calls in this slot.
        self.load_button.clicked.connect(self.load_sample)
        self.tutorials = TutorialController(
            targets={
                "input.load": TutorialTarget(self.load_button, prepare=self.details.hide),
                "input.status": TutorialTarget(self.status, prepare=self.details.hide),
                "details.text": TutorialTarget(lambda: self.details_text, prepare=self.details.show),
            },
            events={"input.loaded": TutorialEvent(self.load_button.clicked)},
            parent=self,
        )
        self.informative = Tutorial("overview", "Conoce la interfaz", (
            TutorialStep("input", "input.load", "Entrada", "Este botón carga los datos de muestra. "
                         "En este recorrido solo lo explicamos: no se puede activar."),
            TutorialStep("status", "input.status", "Estado", "Aquí aparece el estado de los datos. "
                         "No ha hecho falta ejecutar ninguna acción para terminar el recorrido."),
        ))
        self.interactive = load_tutorial(Path(__file__).with_suffix(".toml"))
        self.info_button.clicked.connect(lambda: self.tutorials.start(self.informative))
        self.interactive_button.clicked.connect(lambda: self.tutorials.start(self.interactive))

    def load_sample(self):
        self.status.setText("Ejemplo cargado")


def main():
    app = QApplication(sys.argv)
    apply_theme("auto", app)
    window = DemoWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
