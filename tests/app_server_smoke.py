"""実際のCodex App Server接続。--liveだけモデルを呼び出し利用枠を消費。"""
import argparse
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import hou
from bess_houdini.runtime import Runtime

parser = argparse.ArgumentParser()
parser.add_argument("--live", action="store_true")
args = parser.parse_args()
r = Runtime()


def wait_for(condition, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r.poll()
        if r.status == "エラー":
            raise RuntimeError(str(r.messages[-1]))
        if r.transport and r.transport.process.poll() is not None:
            raise RuntimeError("Codex process exited: " + str(r.messages[-1:]))
        if condition():
            return
        time.sleep(0.05)
    raise TimeoutError(r.status)


with tempfile.TemporaryDirectory(prefix="bess-app-server-") as directory:
    try:
        r.connect("", directory, Path(directory) / "history", True)
        wait_for(lambda: r.ready and r.models and r.authenticated)
        print("ACCOUNT_MODELS_OK", [m["model"] for m in r.models], flush=True)
        ready = []
        r.prepare_thread("gpt-6-sol", lambda _: ready.append(True))
        wait_for(lambda: ready)
        print("DYNAMIC_TOOLS_MCP_DISABLED_OK", flush=True)
        if args.live:
            r.send("Bessの動作確認です。まずhoudini_contextでHoudiniバージョンを確認し、houdini_pythonで /obj に bess_live_test というGeometryを作り、その中にBox SOPを1つ作ってsizeを(1,2,3)に設定してください。resultでノードパスを返してください。この新規テストシーンだけで作業し、保存・外部コマンド・レンダーは不要です。ヘッドレスなので撮影不要です。最後にバージョンと作成結果を日本語一文で答えてください。", "gpt-6-sol", "medium")
            wait_for(lambda: not r.busy, 240)
            geo = hou.node("/obj/bess_live_test")
            assert geo is not None, r.messages[-5:]
            box = next((n for n in geo.children() if n.type().name() == "box"), None)
            assert box is not None
            assert tuple(box.parmTuple("size").eval()) == (1, 2, 3)
            print("LIVE_HOM_OK", flush=True)
            sid = r.session_id
            r.disconnect()
            r.connect("", directory, Path(directory) / "history", False)
            wait_for(lambda: r.ready and r.models and r.authenticated)
            r.load(sid)
            r.send("先ほど作成したGeometryノードの名前だけ答えてください。新しい操作は不要です。", "gpt-6-luna", "medium")
            wait_for(lambda: not r.busy, 180)
            answer = [x["text"] for x in r.messages if x["role"] == "assistant"][-1]
            assert "bess_live_test" in answer, answer
            print("LIVE_RESUME_MODEL_SWITCH_READONLY_OK", flush=True)
            geo.destroy()
        print("BESS_APP_SERVER_OK", flush=True)
    finally:
        r.disconnect()
