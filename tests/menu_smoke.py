"""新規GUIでメニュー登録のみ確認。モデル接続・シーン変更なし。自動終了。"""
import json
import os
from pathlib import Path
import traceback
import hou

output = Path(os.environ["BESS_TEST_ROOT"]) / "test-output/menu-result.json"


def check():
    result = {}
    try:
        result["menu"] = list(hou.pypanel.menuInterfaces())
        assert "bess_houdini" in result["menu"], result["menu"]
        assert hou.pypanel.interfaces()["bess_houdini"].label() == "Bess"
        result["ok"] = True
    except Exception:
        result["ok"] = False
        result["error"] = traceback.format_exc()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    hou.ui.postEventCallback(lambda: hou.exit(exit_code=0 if result["ok"] else 1, suppress_save_prompt=True))


hou.ui.postEventCallback(check)
