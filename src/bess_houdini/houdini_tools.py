"""ライブシーンへの入口。すべて Houdini メインスレッドで実行する。"""
import base64
import contextlib
import io
import json
import math
from pathlib import Path
import threading
import traceback


def tool(name, description, properties=None, required=None):
    return {"type": "function", "name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties or {},
                            "required": required or [], "additionalProperties": False}}


TOOLS = [
    tool("houdini_context", "現在のHoudini、選択ノード、ネットワーク、フレーム、ノード情報を確認。cookしない。",
         {"path": {"type": "string", "description": "調査するノード。省略時は /obj"}}),
    tool("houdini_python", "開いているHoudiniのメインスレッドで短いPythonを実行。hou, math が利用可。print、result、例外を返す。通常のシーン編集をUndoグループにまとめる。",
         {"code": {"type": "string"}, "description": {"type": "string", "description": "短い日本語の操作説明"}}, ["code", "description"]),
    tool("houdini_screenshot", "現在のHoudiniメインウィンドウ全体を撮影。ネットワークとビューポートの目視確認。GUI専用。"),
    tool("houdini_docs", "Houdini同梱ヘルプを英語のノード名・API名でパス検索し、path指定で本文を読む。",
         {"query": {"type": "string"}, "path": {"type": "string"}, "limit": {"type": "integer"}}),
]

INSTRUCTIONS = """あなたは Houdini Indie の内部パネル「Bess」で動く Codex です。日本語で会話してください。
相談には説明し、制作依頼には実際に作業してください。Bessの名称はHarry Houdiniの妻・舞台パートナーに由来します。
ライブシーンは houdini_context で調べ、houdini_python で操作します。外部hythonは別シーンです。MCPは不要です。
ノード型・パラメータは実環境の nodeTypes、parmTemplateGroup や houdini_docs で確かめ、推測で何度も実行しないでください。
houdini_python はメインスレッドで実行します。短い有限の処理に分けてください。sleep、待機ループ、長い同期cook・シミュレーション・renderを実行しないでください。
長い計算は明示的に保存した別ファイルを対象とする外部プロセスなどに分離し、既存の未保存作品を巻き込まないでください。
Windowsのバックグラウンドプロセスに可視コンソールを出さないでください。
現在の選択、ノード、手動変更を毎回確かめ、依頼外の一括削除、上書き保存、Houdini終了はしないでください。
制作は通常のノードとパラメータとして編集可能に保ち、ネットワークを読みやすく整理してください。
Indieのファイルは .hiplc です。保存は依頼された場合に行います。認証情報や会話をhipファイルへ埋め込まないでください。
実行失敗では部分変更が残る可能性があります。再実行する前に現状を確認してください。Undoはファイルや外部コマンドを復元しません。
GUIがある場合は houdini_screenshot で結果も確認してください。ヘッドレスではスクリーンショットは使えません。
"""


def text_result(value, success=True):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return {"success": success, "contentItems": [{"type": "inputText", "text": text[:50000]}]}


class BoundedOutput(io.StringIO):
    def write(self, text):
        available = max(0, 24000 - self.tell())
        super().write(text[:available])
        return len(text)


def context(path="/obj"):
    import hou
    node = hou.node(path or "/obj")
    if node is None:
        raise ValueError("ノードがありません: " + path)
    def info(n):
        return {"path": n.path(), "type": n.type().nameWithCategory(),
                "inputs": [x.path() if x else None for x in n.inputs()],
                "errors": list(n.errors()), "warnings": list(n.warnings())}
    children = node.children()
    result = {"version": hou.applicationVersionString(), "license": str(hou.licenseCategory()),
              "file": hou.hipFile.path(), "unsaved": hou.hipFile.hasUnsavedChanges(),
              "frame": hou.frame(), "range": hou.playbar.frameRange(), "ui": hou.isUIAvailable(),
              "selected": [n.path() for n in hou.selectedNodes()], "node": info(node),
              "children": [info(n) for n in children[:150]], "totalChildren": len(children)}
    if hou.isUIAvailable():
        result["networks"] = [p.pwd().path() for p in hou.ui.paneTabs()
                              if p.type() == hou.paneTabType.NetworkEditor]
    return result


def screenshot():
    import hou
    if not hou.isUIAvailable():
        raise RuntimeError("画像取得にはHoudiniのGUIが必要です。")
    from PySide6 import QtCore
    window = hou.qt.mainWindow()
    pixmap = window.screen().grabWindow(int(window.winId()))
    if pixmap.isNull():
        raise RuntimeError("Houdiniのウィンドウ画像を取得できませんでした。")
    if pixmap.width() > 1600:
        pixmap = pixmap.scaledToWidth(1600, QtCore.Qt.SmoothTransformation)
    data = QtCore.QByteArray()
    buffer = QtCore.QBuffer(data)
    buffer.open(QtCore.QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return {"success": True, "contentItems": [{"type": "inputImage",
            "imageUrl": "data:image/png;base64," + base64.b64encode(bytes(data)).decode("ascii")} ]}


def execute(name, arguments, allow_changes=True):
    if threading.current_thread() is not threading.main_thread():
        return text_result("Houdini操作はメインスレッド専用です。", False)
    try:
        import hou
        if name == "houdini_context":
            return text_result(context(arguments.get("path", "/obj")))
        if name == "houdini_docs":
            from .docs import lookup
            return text_result(lookup(Path(hou.getenv("HFS")) / "houdini/help", **arguments))
        if name == "houdini_screenshot":
            return screenshot()
        if name != "houdini_python":
            raise ValueError("未対応のツール: " + name)
        if not allow_changes:
            raise PermissionError("Houdiniの操作がオフになっています。")
        code = arguments["code"]
        if not isinstance(code, str) or len(code) > 128000:
            raise ValueError("Pythonコードは128000文字以内で指定してください。")
        scope = {"hou": hou, "math": math, "__name__": "__bess_houdini__"}
        output, errors = BoundedOutput(), BoundedOutput()
        exception = None
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                with hou.undos.group("Bess: " + str(arguments.get("description", "Python"))[:100]):
                    exec(compile(code, "<Bess>", "exec"), scope)
            except Exception:
                exception = traceback.format_exc()[-12000:]
        return text_result({"stdout": output.getvalue(), "stderr": errors.getvalue(),
                            "result": scope.get("result"), "error": exception}, exception is None)
    except Exception:
        return text_result(traceback.format_exc()[-12000:], False)
