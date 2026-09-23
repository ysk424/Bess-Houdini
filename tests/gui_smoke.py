"""新規GUIのみで実行する: hindie.steam.exe waitforui tests/gui_smoke.py。自動終了。"""
import base64
import json
import os
from pathlib import Path
import time
import traceback

import hou
from PySide6 import QtCore
import bess_houdini
from bess_houdini.houdini_tools import execute

root = Path(os.environ["BESS_TEST_ROOT"])
output = root / "test-output"
result_path = output / "gui-result.json"
state = {"checks": [], "started": time.monotonic()}


def finish(error=None):
    if state.get("finished"):
        return
    state["finished"] = True
    if state.get("timer"):
        state["timer"].stop()
    if state.get("widget"):
        state["widget"].shutdown()
    result_path.write_text(json.dumps({"ok": error is None, "checks": state["checks"], "error": error}, ensure_ascii=False, indent=2), encoding="utf-8")
    # Qt timeoutのスタック内で親ウィンドウを破棄しない。
    hou.ui.postEventCallback(lambda: hou.exit(exit_code=1 if error else 0, suppress_save_prompt=True))


def check():
    try:
        if time.monotonic() - state["started"] > 75:
            raise TimeoutError("Bess GUI connection timeout")
        widget = state["pane"].activeInterfaceRootWidget()
        if widget is None:
            errors = state["pane"].activeInterfaceScriptErrors()
            if errors:
                raise RuntimeError(errors)
            return
        state["widget"] = widget
        runtime = widget.runtime
        if runtime.status == "エラー":
            raise RuntimeError(str(runtime.messages[-1:]))
        if not runtime.ready or not runtime.authenticated or not runtime.models:
            return
        if "panel_and_connection" not in state["checks"]:
            state["checks"].append("panel_and_connection")
            response = execute("houdini_python", {"code": "result=hou.node('/obj').createNode('geo','bess_gui_undo').path()", "description": "Undo確認"})
            assert response["success"], response
            assert hou.node("/obj/bess_gui_undo")
            hou.undos.performUndo()
            assert hou.node("/obj/bess_gui_undo") is None
            hou.undos.performRedo()
            assert hou.node("/obj/bess_gui_undo")
            state["checks"].append("undo_redo")
            widget.runtime.add("system", "Houdini内の接続・Undo・画面確認テスト")
            widget.render()
            state["capture_after"] = time.monotonic() + 2
            return
        if time.monotonic() < state["capture_after"]:
            return
        response = execute("houdini_screenshot", {})
        assert response["success"], response
        image = base64.b64decode(response["contentItems"][0]["imageUrl"].split(",", 1)[1])
        assert image.startswith(b"\x89PNG")
        (output / "houdini-window.png").write_bytes(image)
        widget.grab().save(str(output / "houdini-panel.png"))
        state["checks"].append("screenshot")
        # パネルを閉じた時に所有するCodexプロセスも終了すること。
        process = runtime.transport.process
        state["pane"].close()
        assert process.poll() is not None
        state["checks"].append("panel_close_process_cleanup")
        finish()
    except Exception:
        finish(traceback.format_exc())


try:
    assert hou.isUIAvailable()
    assert hou.pypanel.interfaces()["bess_houdini"].label() == "Bess"
    assert "bess_houdini" in hou.pypanel.menuInterfaces(), hou.pypanel.menuInterfaces()
    state["checks"].append("toolbar_menu_registration")
    state["pane"] = bess_houdini.show()
    state["timer"] = QtCore.QTimer(hou.qt.mainWindow())
    state["timer"].timeout.connect(check)
    state["timer"].start(100)
except Exception:
    finish(traceback.format_exc())
