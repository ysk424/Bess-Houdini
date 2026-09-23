"""hythonのQtでパネルを描画・検証。オフスクリーン、モデル呼び出しなし。"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6 import QtWidgets
from bess_houdini.panel import BessPanel

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
app.setStyle("Fusion")
with tempfile.TemporaryDirectory(prefix="bess-qt-") as directory:
    panel = BessPanel(storage_root=directory, auto_connect=False)
    panel.resize(620, 900)
    panel.show()
    app.processEvents()
    assert panel.windowTitle() == "Bess"
    assert panel.model.currentData() == "gpt-6-luna"
    panel.preset.setCurrentIndex(1)
    assert panel.model.currentData() == "gpt-6-sol"
    panel.prompt.setPlainText("日本語入力の確認\n二行目")
    assert "二行目" in panel.prompt.toPlainText()
    panel.runtime.add("user", "選択したノードの役割を教えてください。")
    panel.runtime.add("assistant", "現在の選択とネットワークを確認します。\nノードの入力と出力をたどり、処理の流れを説明します。")
    panel.runtime.add("tool", "シーンを確認")
    panel.render()
    app.processEvents()
    output = Path(__file__).resolve().parents[1] / "test-output"
    output.mkdir(exist_ok=True)
    assert panel.grab().save(str(output / "panel.png"))
    panel.resize(420, 760)
    app.processEvents()
    assert panel.grab().save(str(output / "panel-narrow.png"))
    panel.shutdown()
    panel.close()
print("BESS_QT_OK")
