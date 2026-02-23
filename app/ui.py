from dataclasses import asdict
from typing import Any, Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .client import build_curl
from .config import (
    APP_TITLE,
    DEFAULT_BASE_URL,
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_PROMPT,
    LLMRequestConfig,
)
from .storage import ProfileStore
from .utils import estimate_tokens, extract_text_and_usage, pretty_json
from .worker import RequestWorker


class CollapsibleSection(QtWidgets.QWidget):
    def __init__(self, title: str, content: QtWidgets.QWidget, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._toggle = QtWidgets.QToolButton()
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        self._toggle.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

        self._content = content
        self._content.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._toggle)
        layout.addWidget(self._content)

        self._toggle.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self._toggle.setArrowType(
            QtCore.Qt.ArrowType.DownArrow if checked else QtCore.Qt.ArrowType.RightArrow
        )
        self.updateGeometry()


class LLMPanel(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1240, 800)
        self._constrain_to_screen()

        self._profile_store = ProfileStore(path=self._profiles_path())
        self._profiles = self._profile_store.load()

        self._init_ui()
        self._wire_actions()

        self._thread: Optional[QtCore.QThread] = None
        self._worker: Optional[RequestWorker] = None

        self._last_metrics: Dict[str, Any] = {}
        self._last_text = ""
        self._screen_connected = False

    def _constrain_to_screen(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        self.setMaximumSize(geom.width(), geom.height())
        self.resize(min(self.width(), geom.width()), min(self.height(), geom.height()))

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._screen_connected:
            return
        window = self.windowHandle()
        if not window:
            return
        screen = window.screen()
        if screen:
            screen.geometryChanged.connect(self._constrain_to_screen)
            screen.availableGeometryChanged.connect(self._constrain_to_screen)
        window.screenChanged.connect(self._on_screen_changed)
        self._screen_connected = True
        self._constrain_to_screen()

    def _on_screen_changed(self, screen: Optional[QtGui.QScreen]) -> None:
        if screen:
            screen.geometryChanged.connect(self._constrain_to_screen)
            screen.availableGeometryChanged.connect(self._constrain_to_screen)
        self._constrain_to_screen()

    def _profiles_path(self) -> str:
        return str(QtCore.QDir.homePath() + "/.llm_panel_profiles.json")

    def _init_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.analysis_box = QtWidgets.QTextEdit()
        self.analysis_box.setReadOnly(True)
        self.analysis_box.setMinimumHeight(80)
        self.analysis_box.setMaximumHeight(140)
        self.analysis_box.setPlaceholderText("Analisis: status, TTFB, tiempo total, tokens/seg, etc.")

        vlayout = QtWidgets.QVBoxLayout(central)
        vlayout.addWidget(self.splitter, stretch=1)
        vlayout.addWidget(self.analysis_box, stretch=0)

        self.form_widget = QtWidgets.QWidget()
        self.form_layout = QtWidgets.QVBoxLayout(self.form_widget)
        self.form_layout.setContentsMargins(12, 12, 12, 12)
        self.form_layout.setSpacing(10)

        self.response_widget = QtWidgets.QWidget()
        self.response_layout = QtWidgets.QVBoxLayout(self.response_widget)
        self.response_layout.setContentsMargins(12, 12, 12, 12)
        self.response_layout.setSpacing(10)

        self.form_scroll = QtWidgets.QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.form_scroll.setWidget(self.form_widget)

        self.response_scroll = QtWidgets.QScrollArea()
        self.response_scroll.setWidgetResizable(True)
        self.response_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.response_scroll.setWidget(self.response_widget)

        self.splitter.addWidget(self.form_scroll)
        self.splitter.addWidget(self.response_scroll)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([460, 780])

        self._init_profiles_bar()
        self._init_connection_section()
        self._init_request_section()
        self._init_buttons()
        self._init_response_area()

        self.form_layout.addWidget(self.prof_group)
        self.form_layout.addWidget(CollapsibleSection("Conexion", self.conn_body))
        self.form_layout.addWidget(CollapsibleSection("Request", self.req_body))
        self.form_layout.addLayout(self.btn_row)
        self.form_layout.addStretch(1)

        self.status = self.statusBar()
        self.status.showMessage("Listo")

    def _init_profiles_bar(self) -> None:
        self.prof_group = QtWidgets.QGroupBox("Perfiles")
        prof_layout = QtWidgets.QHBoxLayout(self.prof_group)

        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.addItem("(Selecciona perfil)")
        self._refresh_profiles_combo()

        self.profile_name = QtWidgets.QLineEdit("")
        self.profile_name.setPlaceholderText("Nombre para guardar (ej: nvidia-dev)")

        self.save_profile_btn = QtWidgets.QPushButton("Guardar")
        self.load_profile_btn = QtWidgets.QPushButton("Cargar")
        self.delete_profile_btn = QtWidgets.QPushButton("Borrar")

        prof_layout.addWidget(self.profile_combo, stretch=1)
        prof_layout.addWidget(self.profile_name, stretch=1)
        prof_layout.addWidget(self.save_profile_btn)
        prof_layout.addWidget(self.load_profile_btn)
        prof_layout.addWidget(self.delete_profile_btn)

    def _init_connection_section(self) -> None:
        self.conn_body = QtWidgets.QWidget()
        conn_form = QtWidgets.QFormLayout(self.conn_body)

        self.base_url = QtWidgets.QLineEdit(DEFAULT_BASE_URL)
        self.endpoint = QtWidgets.QLineEdit(DEFAULT_ENDPOINT)
        self.api_key = QtWidgets.QLineEdit("")
        self.api_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

        self.timeout_s = QtWidgets.QSpinBox()
        self.timeout_s.setRange(1, 600)
        self.timeout_s.setValue(60)

        self.extra_headers = QtWidgets.QPlainTextEdit("")
        self.extra_headers.setPlaceholderText('Headers extra (JSON dict), ej: {"x-foo":"bar"}')
        self.extra_headers.setMaximumBlockCount(200)

        conn_form.addRow("Base URL", self.base_url)
        conn_form.addRow("Endpoint", self.endpoint)
        conn_form.addRow("API Key", self.api_key)
        conn_form.addRow("Timeout (s)", self.timeout_s)
        conn_form.addRow("Headers extra", self.extra_headers)

    def _init_request_section(self) -> None:
        self.req_body = QtWidgets.QWidget()
        req_form = QtWidgets.QFormLayout(self.req_body)

        self.model = QtWidgets.QLineEdit(DEFAULT_MODEL)

        self.temperature = QtWidgets.QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(0.7)

        self.top_p = QtWidgets.QDoubleSpinBox()
        self.top_p.setRange(0.0, 1.0)
        self.top_p.setSingleStep(0.05)
        self.top_p.setValue(1.0)

        self.max_tokens = QtWidgets.QSpinBox()
        self.max_tokens.setRange(1, 32768)
        self.max_tokens.setValue(512)

        self.stop = QtWidgets.QLineEdit("")
        self.stop.setPlaceholderText('Stop (JSON list). Ej: ["\\n\\nHuman:"]')

        self.stream = QtWidgets.QCheckBox("Stream")
        self.stream.setChecked(False)

        self.system_prompt = QtWidgets.QPlainTextEdit(DEFAULT_SYSTEM_PROMPT)
        self.user_prompt = QtWidgets.QPlainTextEdit(DEFAULT_USER_PROMPT)
        self.system_prompt.setMaximumBlockCount(5000)
        self.user_prompt.setMaximumBlockCount(5000)

        req_form.addRow("Model", self.model)
        req_form.addRow("Temperature", self.temperature)
        req_form.addRow("Top-p", self.top_p)
        req_form.addRow("Max tokens", self.max_tokens)
        req_form.addRow("Stop", self.stop)
        req_form.addRow("Streaming", self.stream)
        req_form.addRow("System", self.system_prompt)
        req_form.addRow("User", self.user_prompt)

    def _init_buttons(self) -> None:
        self.btn_row = QtWidgets.QHBoxLayout()
        self.send_btn = QtWidgets.QPushButton("Send")
        self.clear_btn = QtWidgets.QPushButton("Clear")

        self.copy_curl_btn = QtWidgets.QPushButton("Copy cURL (mask)")
        self.copy_curl_reveal_btn = QtWidgets.QPushButton("Copy cURL (reveal key)")
        self.copy_resp_btn = QtWidgets.QPushButton("Copy response")

        self.btn_row.addWidget(self.send_btn)
        self.btn_row.addWidget(self.clear_btn)
        self.btn_row.addStretch(1)
        self.btn_row.addWidget(self.copy_curl_btn)
        self.btn_row.addWidget(self.copy_curl_reveal_btn)
        self.btn_row.addWidget(self.copy_resp_btn)

    def _init_response_area(self) -> None:
        self.response_tabs = QtWidgets.QTabWidget()
        self.response_text = QtWidgets.QPlainTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setPlaceholderText("Aqui saldra la respuesta (texto / streaming).")

        self.response_json = QtWidgets.QPlainTextEdit()
        self.response_json.setReadOnly(True)
        self.response_json.setPlaceholderText("Aqui saldra el JSON parseado (si aplica).")

        self.response_meta = QtWidgets.QPlainTextEdit()
        self.response_meta.setReadOnly(True)
        self.response_meta.setPlaceholderText("Aqui saldran status, headers, payload, etc.")

        self.response_tabs.addTab(self.response_text, "Respuesta (texto)")
        self.response_tabs.addTab(self.response_json, "Respuesta (JSON)")
        self.response_tabs.addTab(self.response_meta, "Meta")
        self.response_layout.addWidget(self.response_tabs)

    def _wire_actions(self) -> None:
        self.send_btn.clicked.connect(self.on_send)
        self.clear_btn.clicked.connect(self.on_clear)
        self.copy_curl_btn.clicked.connect(lambda: self.on_copy_curl(reveal=False))
        self.copy_curl_reveal_btn.clicked.connect(lambda: self.on_copy_curl(reveal=True))
        self.copy_resp_btn.clicked.connect(self.on_copy_response)

        self.save_profile_btn.clicked.connect(self.on_save_profile)
        self.load_profile_btn.clicked.connect(self.on_load_profile)
        self.delete_profile_btn.clicked.connect(self.on_delete_profile)

    def _refresh_profiles_combo(self) -> None:
        current = self.profile_combo.currentText() if hasattr(self, "profile_combo") else None
        if hasattr(self, "profile_combo"):
            self.profile_combo.blockSignals(True)
            self.profile_combo.clear()
            self.profile_combo.addItem("(Selecciona perfil)")
            for name in sorted(self._profiles.keys()):
                self.profile_combo.addItem(name)
            if current and current in self._profiles:
                idx = self.profile_combo.findText(current)
                if idx >= 0:
                    self.profile_combo.setCurrentIndex(idx)
            self.profile_combo.blockSignals(False)

    def _get_cfg(self) -> LLMRequestConfig:
        return LLMRequestConfig(
            base_url=self.base_url.text(),
            endpoint=self.endpoint.text(),
            api_key=self.api_key.text(),
            model=self.model.text(),
            system_prompt=self.system_prompt.toPlainText(),
            user_prompt=self.user_prompt.toPlainText(),
            temperature=float(self.temperature.value()),
            max_tokens=int(self.max_tokens.value()),
            top_p=float(self.top_p.value()),
            stop=self.stop.text(),
            timeout_s=int(self.timeout_s.value()),
            extra_headers=self.extra_headers.toPlainText(),
            stream=bool(self.stream.isChecked()),
        )

    def _apply_cfg(self, cfg_dict: Dict[str, Any]) -> None:
        self.base_url.setText(cfg_dict.get("base_url", self.base_url.text()))
        self.endpoint.setText(cfg_dict.get("endpoint", self.endpoint.text()))
        if "api_key" in cfg_dict and cfg_dict["api_key"] is not None:
            self.api_key.setText(cfg_dict.get("api_key", ""))
        self.model.setText(cfg_dict.get("model", self.model.text()))
        self.system_prompt.setPlainText(cfg_dict.get("system_prompt", self.system_prompt.toPlainText()))
        self.user_prompt.setPlainText(cfg_dict.get("user_prompt", self.user_prompt.toPlainText()))
        if "temperature" in cfg_dict:
            self.temperature.setValue(float(cfg_dict["temperature"]))
        if "max_tokens" in cfg_dict:
            self.max_tokens.setValue(int(cfg_dict["max_tokens"]))
        if "top_p" in cfg_dict:
            self.top_p.setValue(float(cfg_dict["top_p"]))
        self.stop.setText(cfg_dict.get("stop", self.stop.text()))
        if "timeout_s" in cfg_dict:
            self.timeout_s.setValue(int(cfg_dict["timeout_s"]))
        self.extra_headers.setPlainText(cfg_dict.get("extra_headers", self.extra_headers.toPlainText()))
        if "stream" in cfg_dict:
            self.stream.setChecked(bool(cfg_dict["stream"]))

    def on_save_profile(self) -> None:
        name = self.profile_name.text().strip() or self.profile_combo.currentText().strip()
        if not name or name == "(Selecciona perfil)":
            self.status.showMessage("Pon un nombre de perfil para guardar")
            return

        cfg = self._get_cfg()
        data = asdict(cfg)

        self._profiles[name] = data
        self._profile_store.save(self._profiles)
        self._refresh_profiles_combo()
        idx = self.profile_combo.findText(name)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self.status.showMessage(f"Perfil guardado: {name}")

    def on_load_profile(self) -> None:
        name = self.profile_combo.currentText().strip()
        if not name or name == "(Selecciona perfil)":
            self.status.showMessage("Selecciona un perfil para cargar")
            return
        cfg = self._profiles.get(name)
        if not isinstance(cfg, dict):
            self.status.showMessage("Perfil no encontrado")
            return
        self._apply_cfg(cfg)
        self.status.showMessage(f"Perfil cargado: {name}")

    def on_delete_profile(self) -> None:
        name = self.profile_combo.currentText().strip()
        if not name or name == "(Selecciona perfil)":
            self.status.showMessage("Selecciona un perfil para borrar")
            return
        if name in self._profiles:
            del self._profiles[name]
            self._profile_store.save(self._profiles)
            self._refresh_profiles_combo()
            self.status.showMessage(f"Perfil borrado: {name}")

    def on_clear(self) -> None:
        self.response_text.clear()
        self.response_json.clear()
        self.response_meta.clear()
        self.analysis_box.clear()
        self._last_metrics = {}
        self._last_text = ""
        self.status.showMessage("Limpio")

    def on_copy_response(self) -> None:
        txt = self.response_text.toPlainText().strip()
        if not txt:
            txt = self.response_json.toPlainText().strip()
        QtWidgets.QApplication.clipboard().setText(txt)
        self.status.showMessage("Copiado al portapapeles")

    def on_copy_curl(self, reveal: bool) -> None:
        cfg = self._get_cfg()
        curl = build_curl(cfg, reveal_key=reveal)
        QtWidgets.QApplication.clipboard().setText(curl)
        self.status.showMessage("cURL copiado" + (" (con key)" if reveal else " (key enmascarada)"))

    def on_send(self) -> None:
        cfg = self._get_cfg()

        if not cfg.base_url.strip():
            self.status.showMessage("Falta Base URL")
            return
        if not cfg.model.strip():
            self.status.showMessage("Falta Model")
            return
        if not cfg.user_prompt.strip():
            self.status.showMessage("Falta User prompt")
            return

        self.response_text.setPlainText("")
        self.response_json.setPlainText("")
        self.response_meta.setPlainText("")
        self.analysis_box.setPlainText("")
        self._last_metrics = {}
        self._last_text = ""

        self.send_btn.setEnabled(False)
        self.status.showMessage("Enviando request...")

        self._thread = QtCore.QThread()
        self._worker = RequestWorker(cfg)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.partial.connect(self.on_partial)
        self._worker.finished.connect(self.on_result)
        self._worker.error.connect(self.on_error)

        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._cleanup_worker)

        self._thread.start()

    def _cleanup_worker(self) -> None:
        self._worker = None
        self._thread = None
        self.send_btn.setEnabled(True)

    def on_error(self, msg: str) -> None:
        self.send_btn.setEnabled(True)
        self.status.showMessage("Error")
        self.analysis_box.setPlainText(msg)

    def on_partial(self, partial_text: str, metrics: dict) -> None:
        self._last_text = partial_text
        self._last_metrics = metrics or {}

        self.response_text.setPlainText(partial_text)
        cursor = self.response_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.response_text.setTextCursor(cursor)

        self._render_analysis(streaming=True)

    def _render_analysis(self, streaming: bool) -> None:
        status = self._last_metrics.get("status_code")
        elapsed = self._last_metrics.get("elapsed_s")
        ttfb = self._last_metrics.get("ttfb_s")

        text = self._last_text or self.response_text.toPlainText()
        tok_est = estimate_tokens(text)
        tps = None
        if elapsed and elapsed > 0:
            tps = tok_est / elapsed

        lines = []
        if status is not None:
            lines.append(f"Status: {status}")
        if elapsed is not None:
            lines.append(f"Tiempo total: {float(elapsed):.3f}s")
        if streaming:
            if ttfb is None:
                lines.append("TTFB: (aun no llego el primer token)")
            else:
                lines.append(f"TTFB (primer token): {float(ttfb):.3f}s")
        if tok_est:
            lines.append(f"Tokens estimados (heuristica): {tok_est}")
        if tps is not None:
            lines.append(f"Tokens/seg estimados: {tps:.2f}")

        if status == 429:
            lines.append("Nota: 429 = rate limit (demasiadas requests).")

        self.analysis_box.setPlainText("\n".join(lines))

    def on_result(self, result: dict) -> None:
        self.send_btn.setEnabled(True)

        status_code = result.get("status_code", 0)
        elapsed = float(result.get("elapsed_s", 0.0))
        ttfb_s = result.get("ttfb_s", None)

        resp_json = result.get("response_json")
        resp_text = result.get("response_text", "")
        streamed_text = result.get("streamed_text", "")

        if streamed_text:
            self.response_text.setPlainText(streamed_text)
        else:
            extracted_text, _usage = extract_text_and_usage(resp_json)
            if extracted_text.strip():
                self.response_text.setPlainText(extracted_text)
            else:
                self.response_text.setPlainText(resp_text)

        if resp_json is not None:
            self.response_json.setPlainText(pretty_json(resp_json))
        else:
            self.response_json.setPlainText("(No JSON parseado)")

        meta = {
            "url": result.get("url"),
            "status_code": status_code,
            "elapsed_s": elapsed,
            "ttfb_s": ttfb_s,
            "response_headers": result.get("headers", {}),
            "request_payload": result.get("request_payload", {}),
        }
        self.response_meta.setPlainText(pretty_json(meta))

        self._last_metrics = {"status_code": status_code, "elapsed_s": elapsed, "ttfb_s": ttfb_s}
        self._last_text = streamed_text or self.response_text.toPlainText()
        self._render_analysis(streaming=bool(result.get("streamed_text")))

        self.status.showMessage(f"OK ({status_code}) en {elapsed:.2f}s")


def run_app() -> None:
    app = QtWidgets.QApplication([])
    w = LLMPanel()
    w.show()
    app.exec()
