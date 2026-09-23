"""未確定文字を段階的に送り、通信更新中もIME状態が保たれることを検証。"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from bess_houdini.panel import BessPanel

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
with tempfile.TemporaryDirectory() as directory:
    panel = BessPanel(storage_root=directory, auto_connect=False)
    panel.resize(600, 900)
    panel.show()
    app.processEvents()
    QtTest.QTest.mouseClick(panel.prompt.viewport(), QtCore.Qt.LeftButton)
    assert type(panel.prompt) is QtWidgets.QPlainTextEdit
    for i, text in enumerate(["に", "にほ", "にほん", "にほんご", "にほんごのにゅうりょく", "日本語の入力を確認しています"]):
        app.sendEvent(panel.prompt, QtGui.QInputMethodEvent(text, []))
        panel.runtime.add("assistant", "応答表示 " + str(i))
        QtTest.QTest.qWait(180)
        assert panel.prompt.document().firstBlock().layout().preeditAreaText() == text
        assert panel.prompt.toPlainText() == ""
        assert panel.prompt.hasFocus()
    event = QtGui.QInputMethodEvent()
    event.setCommitString("日本語の入力を確認しています")
    app.sendEvent(panel.prompt, event)
    assert panel.prompt.toPlainText() == "日本語の入力を確認しています"
    # 追加指示の受理待ちでも入力欄を読み取り専用に変更しない。
    panel.runtime.steering = True
    panel.render()
    assert not panel.prompt.isReadOnly()
    QtTest.QTest.keyClick(panel.prompt, QtCore.Qt.Key_Return)
    QtTest.QTest.keyClicks(panel.prompt, "next draft")
    assert panel.prompt.toPlainText().endswith("\nnext draft")
    # 状態に変化がないポーリングでは、UIのsetterを呼び出さない。
    calls = []
    panel.status.setText = lambda value: calls.append(value)
    panel.prompt.setReadOnly = lambda value: calls.append(value)
    QtTest.QTest.qWait(200)
    assert calls == [], calls
    panel.shutdown()
    panel.close()
print("BESS_IME_PREEDIT_OK")
