"""Houdini Python Panel。QtタイマーからのみHOMと会話状態を扱う。"""
import html
import json
from pathlib import Path

import hou
from PySide6 import QtCore, QtGui, QtWidgets

from .runtime import Runtime

PRESETS = [("問い合わせ", "gpt-6-luna", "medium"),
           ("制作", "gpt-6-sol", "medium"),
           ("難しい仕事", "gpt-6-astra", "xhigh")]


class BessPanel(QtWidgets.QWidget):
    def __init__(self, parent=None, storage_root=None, auto_connect=True):
        super().__init__(parent)
        self.setObjectName("BessPanel")
        self.setWindowTitle("Bess")
        self.runtime = Runtime()
        self.root = Path(storage_root or (Path(hou.getenv("HOUDINI_USER_PREF_DIR")) / "bess_houdini"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.root / "settings.json"
        self.runtime.storage = self.root / "conversations"
        self.runtime.storage.mkdir(exist_ok=True)
        self._revision = -1
        self._view_state = None
        self._model_signature = None
        self._request_id = None
        self._closed = False
        self._answers = {}
        try:
            settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            settings = {}
        if hou.hipFile.isNewFile():
            workspace = self.root / "workspace"
            workspace.mkdir(exist_ok=True)
            default_cwd = str(workspace)
        else:
            default_cwd = str(Path(hou.expandString("$HIP")).resolve())
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Bess")
        title.setStyleSheet("font-size: 25px; font-weight: 600; color: #ecc590;")
        subtitle = QtWidgets.QLabel("Houdini の魔術パートナー")
        header.addWidget(title)
        header.addWidget(subtitle)
        header.addStretch()
        self.connect_button = self.button("接続", self.toggle_connection)
        header.addWidget(self.connect_button)
        layout.addLayout(header)
        self.status = QtWidgets.QLabel("未接続")
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.PlainText)
        layout.addWidget(self.status)

        modelrow = QtWidgets.QHBoxLayout()
        self.preset = QtWidgets.QComboBox()
        for label, model, effort in PRESETS:
            self.preset.addItem(label, (model, effort))
        self.model = QtWidgets.QComboBox()
        for _, model, _ in PRESETS:
            self.model.addItem(model, model)
        self.effort = QtWidgets.QComboBox()
        self.effort.addItems(["low", "medium", "high", "xhigh"])
        self.effort.setCurrentText("medium")
        modelrow.addWidget(self.preset)
        modelrow.addWidget(self.model, 1)
        modelrow.addWidget(self.effort)
        layout.addLayout(modelrow)
        self.preset.currentIndexChanged.connect(self.apply_preset)
        self.model.currentIndexChanged.connect(self.update_efforts)

        actions = QtWidgets.QHBoxLayout()
        self.new_button = self.button("新しい会話", self.new_chat)
        actions.addWidget(self.new_button)
        self.history = QtWidgets.QComboBox()
        self.history.setMinimumContentsLength(8)
        self.history.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        actions.addWidget(self.history, 1)
        self.history_button = self.button("開く", self.open_history)
        actions.addWidget(self.history_button)
        actions.addWidget(self.button("コピー", self.copy_chat))
        layout.addLayout(actions)
        self.transcript = QtWidgets.QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setOpenLinks(False)
        self.transcript.setMinimumHeight(200)
        self.transcript.setStyleSheet("QTextBrowser {background: #202329; border: 1px solid #454950; border-radius: 6px; padding: 10px;}")
        layout.addWidget(self.transcript, 1)
        self.follow = QtWidgets.QCheckBox("最新の発言を追う")
        self.follow.setChecked(True)
        layout.addWidget(self.follow)
        self.question = QtWidgets.QGroupBox("Codexからの確認")
        self.question_layout = QtWidgets.QVBoxLayout(self.question)
        self.question.hide()
        layout.addWidget(self.question)
        prompt_label = QtWidgets.QLabel("メッセージ（入力後に「送信」を押してください）")
        layout.addWidget(prompt_label)
        # キー処理やIME処理を上書きしない。未確定文字はQt/OSに任せる。
        self.prompt = QtWidgets.QPlainTextEdit()
        self.prompt.setObjectName("bess_message_input")
        prompt_label.setBuddy(self.prompt)
        self.prompt.setMinimumHeight(90)
        self.prompt.setMaximumHeight(160)
        layout.addWidget(self.prompt)
        # HoudiniはPython Panelをクリックした際にルートへフォーカスを戻す。
        # そのフォーカスを入力欄へ渡し、Houdiniのペインにキーを奪われないようにする。
        self.setFocusProxy(self.prompt)
        sendrow = QtWidgets.QHBoxLayout()
        self.settings_toggle = QtWidgets.QToolButton()
        self.settings_toggle.setText("設定")
        self.settings_toggle.setCheckable(True)
        sendrow.addWidget(self.settings_toggle)
        self.login_button = self.button("ChatGPTでログイン", lambda: self.runtime.login())
        sendrow.addWidget(self.login_button)
        sendrow.addStretch()
        self.stop_button = self.button("停止", lambda: self.runtime.interrupt())
        sendrow.addWidget(self.stop_button)
        self.paste_button = self.button("ペースト", self.paste_prompt)
        self.paste_button.setToolTip("クリップボードの文章を入力欄に貼り付けます")
        sendrow.addWidget(self.paste_button)
        self.send_button = self.button("送信", self.send)
        self.send_button.setStyleSheet("QPushButton {background: #86633a; color: white; padding: 7px 22px;}")
        sendrow.addWidget(self.send_button)
        layout.addLayout(sendrow)

        self.settings_group = QtWidgets.QGroupBox("接続設定")
        form = QtWidgets.QFormLayout(self.settings_group)
        self.cwd = QtWidgets.QLineEdit(settings.get("cwd", default_cwd))
        cwdrow = QtWidgets.QHBoxLayout()
        cwdrow.addWidget(self.cwd)
        cwdrow.addWidget(self.button("選択", self.pick_cwd))
        form.addRow("作業フォルダー", cwdrow)
        self.executable = QtWidgets.QLineEdit(settings.get("executable", ""))
        self.executable.setPlaceholderText("空欄ならCodex CLIを自動検出")
        form.addRow("codex.exe", self.executable)
        self.allow = QtWidgets.QCheckBox("PC・Houdiniの操作を許可")
        self.allow.setChecked(settings.get("allow_changes", True))
        form.addRow(self.allow)
        hint = QtWidgets.QLabel("変更は再接続で反映します。操作をオフにすると読み取り専用になります。\n長いPython処理は実行が戻るまで停止できません。")
        hint.setWordWrap(True)
        form.addRow(hint)
        layout.addWidget(self.settings_group)
        self.settings_group.hide()
        self.settings_toggle.toggled.connect(self.settings_group.setVisible)
        self.refresh_histories()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)
        self.destroyed.connect(self.runtime.disconnect)
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.shutdown)
        self.render()
        if auto_connect:
            QtCore.QTimer.singleShot(0, lambda: self.guard(self.toggle_connection) if not self._closed else None)

    def button(self, label, callback):
        button = QtWidgets.QPushButton(label)
        button.clicked.connect(lambda _=False: self.guard(callback))
        return button

    def guard(self, callback):
        try:
            callback()
        except Exception as error:
            self.runtime.add("system", str(error))
        self.render()

    def pick_cwd(self):
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, "作業フォルダー", self.cwd.text())
        if selected:
            self.cwd.setText(selected)

    def toggle_connection(self):
        if self.runtime.transport:
            self.runtime.disconnect()
        else:
            settings = {"cwd": self.cwd.text(), "executable": self.executable.text(), "allow_changes": self.allow.isChecked()}
            self.settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
            self.runtime.connect(settings["executable"], settings["cwd"], self.root / "conversations", settings["allow_changes"])

    def apply_preset(self, _=None):
        model, effort = self.preset.currentData()
        index = self.model.findData(model)
        if index < 0:
            self.model.addItem(model + "（利用可否未確認）", model)
            index = self.model.count() - 1
        self.model.setCurrentIndex(index)
        self.update_efforts()
        if self.effort.findText(effort) < 0:
            self.effort.addItem(effort)
        self.effort.setCurrentText(effort)

    def update_efforts(self, _=None):
        model = next((m for m in self.runtime.models if m["model"] == self.model.currentData()), None)
        if not model:
            return
        selected = self.effort.currentText()
        self.effort.clear()
        self.effort.addItems([e["reasoningEffort"] for e in model.get("supportedReasoningEfforts", [])])
        self.effort.setCurrentText(selected if self.effort.findText(selected) >= 0 else model.get("defaultReasoningEffort", "medium"))

    def paste_prompt(self):
        self.prompt.paste()
        self.prompt.setFocus(QtCore.Qt.MouseFocusReason)

    def send(self):
        text = self.prompt.toPlainText().strip()
        if not text:
            return
        if self.runtime.busy:
            def accepted():
                if self.prompt.toPlainText().strip() == text:
                    self.prompt.clear()
            self.runtime.steer(text, accepted)
        else:
            self.runtime.send(text, self.model.currentData(), self.effort.currentText())
            self.prompt.clear()

    def new_chat(self):
        self.runtime.new_chat()
        self.refresh_histories()

    def refresh_histories(self):
        selected = self.history.currentData()
        self.history.clear()
        self.history.addItem("会話履歴", None)
        for session, title, _ in self.runtime.histories():
            self.history.addItem(title, session)
        index = self.history.findData(selected)
        self.history.setCurrentIndex(max(0, index))

    def open_history(self):
        if self.history.currentData():
            self.runtime.load(self.history.currentData())
            self.cwd.setText(self.runtime.cwd)

    def copy_chat(self):
        QtWidgets.QApplication.clipboard().setText("\n\n".join(x["role"] + ": " + x["text"] for x in self.runtime.messages))

    def tick(self):
        if self._closed:
            return
        was_busy = self.runtime.busy
        self.runtime.poll()
        if was_busy and not self.runtime.busy:
            self.refresh_histories()
        self.render()

    def render(self):
        r = self.runtime
        signature = [(m["model"], m.get("supportedReasoningEfforts", [])) for m in r.models]
        view_state = (r.revision, bool(r.transport), r.status, r.account, r.resolved_model,
                      r.resolved_effort, r.tokens, r.ready, r.authenticated, r.busy,
                      r.interrupted, r.steering, r.turn_id, repr(signature),
                      tuple(request["id"] for request in r.requests))
        if self._view_state == view_state:
            return
        self._view_state = view_state
        self.connect_button.setText("切断" if r.transport else "接続")
        self.status.setText(r.status + "  ·  " + r.account +
                            ("\n" + r.resolved_model + " / " + r.resolved_effort if r.resolved_model else ""))
        self.status.setToolTip(r.tokens)
        self.login_button.setEnabled(r.ready and not r.authenticated)
        self.stop_button.setEnabled(r.busy and not r.interrupted)
        self.send_button.setText("追加指示を送る" if r.busy else "送信")
        self.send_button.setEnabled(r.ready and r.authenticated and not r.steering and (not r.busy or bool(r.turn_id) and not r.interrupted))
        # 通信待ちでも入力欄の状態は変更しない。次の文章を書き続けられる。
        self.new_button.setEnabled(not r.busy)
        self.history_button.setEnabled(not r.busy)
        self.settings_group.setEnabled(not r.transport)
        for control in (self.preset, self.model, self.effort):
            control.setEnabled(not r.busy)
        if signature and signature != self._model_signature:
            selected = self.model.currentData()
            self._model_signature = signature
            self.model.blockSignals(True)
            self.model.clear()
            for m in r.models:
                self.model.addItem(m.get("displayName", m["model"]), m["model"])
            if self.model.findData(selected) < 0:
                self.model.addItem(selected + "（利用不可）", selected)
            self.model.setCurrentIndex(self.model.findData(selected))
            self.model.blockSignals(False)
            self.update_efforts()
        self.render_question()
        if self._revision == r.revision:
            return
        self._revision = r.revision
        bar = self.transcript.verticalScrollBar()
        old_position = bar.value()
        labels = {"user": "あなた", "assistant": "Bess", "tool": "作業", "system": "お知らせ"}
        blocks = []
        for item in r.messages:
            color = "#ecc590" if item["role"] == "assistant" else "#aab8c8"
            blocks.append('<p style="color:' + color + '; margin-bottom:4px"><b>' + labels.get(item["role"], item["role"]) + '</b></p><p style="white-space:pre-wrap; color:#e1e4e8; margin-top:0; margin-bottom:18px">' + html.escape(item["text"]) + '</p>')
        if not blocks:
            blocks = ['<p style="color:#ecc590;font-size:18px">何を作りましょうか。</p><p style="color:#b8bec8">ノードの相談から、シーンの制作まで。<br>現在のHoudiniを確認しながら作業します。</p>']
        self.transcript.setHtml("".join(blocks))
        bar.setValue(bar.maximum() if self.follow.isChecked() else old_position)

    def render_question(self):
        request = self.runtime.requests[0] if self.runtime.requests else None
        request_id = request["id"] if request else None
        if request_id == self._request_id:
            return
        self._request_id = request_id
        while self.question_layout.count():
            item = self.question_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.question.setVisible(request is not None)
        self._answers = {}
        if not request:
            return
        params = request["params"]
        if request["method"] == "item/tool/requestUserInput":
            for q in params.get("questions", []):
                label = QtWidgets.QLabel(q.get("question", q["id"]))
                label.setTextFormat(QtCore.Qt.PlainText)
                label.setWordWrap(True)
                self.question_layout.addWidget(label)
                edit = QtWidgets.QComboBox()
                edit.setEditable(True)
                for option in q.get("options") or []:
                    edit.addItem(option["label"])
                self._answers[q["id"]] = edit
                self.question_layout.addWidget(edit)
            self.question_layout.addWidget(self.button("回答する", lambda: self.runtime.answer(True,
                {key: {"answers": [edit.currentText()]} for key, edit in self._answers.items()})))
        else:
            label = QtWidgets.QLabel(str(params.get("reason") or params.get("command") or request["method"]))
            label.setTextFormat(QtCore.Qt.PlainText)
            label.setWordWrap(True)
            self.question_layout.addWidget(label)
            # 許可範囲の拡大はこのパネルから行わない。
            self.question_layout.addWidget(self.button("辞退して続ける", lambda: self.runtime.answer(False)))

    def shutdown(self):
        if not self._closed:
            self._closed = True
            self.timer.stop()
            self.runtime.disconnect()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
