"""新規GUIのPython Panel内でクリック・入力を検証。Codexには接続しない。"""
import json
import os
from pathlib import Path
import time
import traceback
import hou
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from bess_houdini.runtime import Runtime

Runtime.connect = lambda *args, **kwargs: None
output = Path(os.environ["BESS_TEST_ROOT"]) / "test-output/input-result.json"
state = {"phase": 0, "observations": [], "time": time.monotonic()}


def observe(label):
    w = state["widget"]
    focus = QtWidgets.QApplication.focusWidget()
    state["observations"].append({"label": label, "focused": w.prompt.hasFocus(),
        "focusWidget": type(focus).__name__, "enabled": w.prompt.isEnabled(),
        "readOnly": w.prompt.isReadOnly(), "focusPolicy": int(w.prompt.focusPolicy()),
        "text": w.prompt.toPlainText(), "flags": str(w.prompt.textInteractionFlags())})


def finish(error=None):
    state["timer"].stop()
    output.write_text(json.dumps({"ok": error is None, "observations": state["observations"], "error": error}, ensure_ascii=False, indent=2), encoding="utf-8")
    if state.get("widget"):
        state["widget"].shutdown()
    hou.ui.postEventCallback(lambda: hou.exit(exit_code=1 if error else 0, suppress_save_prompt=True))


def check():
    try:
        phase = state["phase"]
        if phase == 0:
            # waitforui直後はHoudiniがウィンドウ配置を復元中のことがある。
            if time.monotonic() - state["time"] < 5:
                return
            pane = hou.ui.curDesktop().paneTabOfType(hou.paneTabType.SceneViewer).setType(hou.paneTabType.PythonPanel)
            pane.setActiveInterface(hou.pypanel.interfaces()["bess_houdini"])
            state["pane"] = pane
            state["widget"] = pane.activeInterfaceRootWidget()
            state["phase"] = 1
            state["time"] = time.monotonic()
            return
        if time.monotonic() - state["time"] < 2:
            return
        w = state["widget"]
        if phase == 1:
            w.runtime.ready = w.runtime.authenticated = True
            w.render()
            QtWidgets.QApplication.setActiveWindow(hou.qt.mainWindow())
            observe("before_click")
            QtTest.QTest.mouseClick(w.prompt.viewport(), QtCore.Qt.LeftButton)
            observe("after_click")
            state["phase"] = 2
            state["time"] = time.monotonic()
        elif phase == 2:
            observe("after_polling")
            focus = QtWidgets.QApplication.focusWidget()
            assert focus is w.prompt, state["observations"]
            QtTest.QTest.keyClicks(focus, "hello")
            QtTest.QTest.keyClick(focus, QtCore.Qt.Key_Return)
            state["preedits"] = ["に", "にほ", "にほん", "にほんご", "にほんごの", "にほんごのにゅうりょく", "日本語の入力を確認"]
            state["preedit_index"] = 0
            QtWidgets.QApplication.sendEvent(focus, QtGui.QInputMethodEvent(state["preedits"][0], []))
            state["phase"] = 2.5
            state["time"] = time.monotonic()
        elif phase == 2.5:
            previous = state["preedits"][state["preedit_index"]]
            block = w.prompt.textCursor().block()
            assert block.layout().preeditAreaText() == previous, (previous, block.layout().preeditAreaText())
            assert w.prompt.toPlainText() == "hello\n"
            assert w.prompt.hasFocus()
            state["preedit_index"] += 1
            index = state["preedit_index"]
            if index < len(state["preedits"]):
                QtWidgets.QApplication.sendEvent(w.prompt, QtGui.QInputMethodEvent(state["preedits"][index], []))
                # 応答表示と通常のポーリングが未確定文字を壊さないこと。
                w.runtime.add("assistant", "入力中の画面更新テスト " + str(index))
                state["time"] = time.monotonic()
                return
            event = QtGui.QInputMethodEvent()
            event.setCommitString(state["preedits"][-1])
            QtWidgets.QApplication.sendEvent(w.prompt, event)
            observe("after_input")
            assert w.prompt.toPlainText() == "hello\n日本語の入力を確認", state["observations"]
            state["phase"] = 3
            state["time"] = time.monotonic()
        elif phase == 3:
            observe("input_persisted")
            assert w.prompt.toPlainText() == "hello\n日本語の入力を確認"
            w.grab().save(str(output.with_suffix(".png")))
            w.settings_toggle.setChecked(True)
            state["phase"] = 4
            state["time"] = time.monotonic()
        elif phase == 4:
            QtTest.QTest.mouseClick(w.cwd, QtCore.Qt.LeftButton)
            assert QtWidgets.QApplication.focusWidget() is w.cwd
            w.cwd.selectAll()
            QtTest.QTest.keyClicks(w.cwd, "C:/test-workspace")
            assert w.cwd.text() == "C:/test-workspace"
            w.settings_toggle.setChecked(False)
            QtTest.QTest.mouseClick(w.prompt.viewport(), QtCore.Qt.LeftButton)
            state["phase"] = 5
            state["time"] = time.monotonic()
        else:
            observe("after_settings_return")
            assert QtWidgets.QApplication.focusWidget() is w.prompt
            assert w.prompt.toPlainText() == "hello\n日本語の入力を確認"
            finish()
    except Exception:
        finish(traceback.format_exc())


state["timer"] = QtCore.QTimer(hou.qt.mainWindow())
state["timer"].timeout.connect(check)
state["timer"].start(100)
