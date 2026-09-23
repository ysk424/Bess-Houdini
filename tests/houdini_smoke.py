"""新規hython内でHOM・停止時の権限・履歴・ヘルプ検索を検証。モデル利用なし。"""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import hou
from bess_houdini.houdini_tools import execute
from bess_houdini.runtime import Runtime


def content(result):
    return json.loads(result["contentItems"][0]["text"])


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.replies = []

    def reply(self, request_id, result):
        self.replies.append((request_id, result))

    def request(self, method, params):
        self.calls.append((method, params))
        return len(self.calls)

    def close(self):
        pass


class HoudiniTests(unittest.TestCase):
    def setUp(self):
        self.node = hou.node("/obj").createNode("geo", "bess_test")

    def tearDown(self):
        if self.node:
            self.node.destroy()

    def test_python_and_context(self):
        result = execute("houdini_python", {"description": "箱を作る",
            "code": f"box=hou.node({self.node.path()!r}).createNode('box'); box.parmTuple('size').set((1,2,3)); print('作成'); result=box.path()"})
        self.assertTrue(result["success"], result)
        path = content(result)["result"]
        self.assertEqual(tuple(hou.node(path).parmTuple("size").eval()), (1, 2, 3))
        info = content(execute("houdini_context", {"path": self.node.path()}))
        self.assertEqual(info["children"][0]["path"], path)
        self.assertIn("Indie", info["license"])

    def test_error_preserves_output_and_partial_edit(self):
        result = execute("houdini_python", {"description": "例外確認",
            "code": f"hou.node({self.node.path()!r}).createNode('null','partial'); print('before'); raise ValueError('test exception')"})
        self.assertFalse(result["success"])
        self.assertIn("before", content(result)["stdout"])
        self.assertIn("test exception", content(result)["error"])
        self.assertIsNotNone(self.node.node("partial"))

    def test_readonly_and_background_rejected(self):
        code = {"description": "拒否確認", "code": f"hou.node({self.node.path()!r}).createNode('null','forbidden')"}
        self.assertFalse(execute("houdini_python", code, False)["success"])
        results = []
        worker = threading.Thread(target=lambda: results.append(execute("houdini_python", code)))
        worker.start()
        worker.join()
        self.assertFalse(results[0]["success"])
        self.assertIsNone(self.node.node("forbidden"))

    def test_stop_and_stale_turn_rejected(self):
        r = Runtime()
        r.transport = FakeTransport()
        r.thread_id, r.turn_id, r.busy = "thread", "current", True
        event = {"id": 42, "method": "item/tool/call", "params": {"threadId": "thread", "turnId": "old",
                 "tool": "houdini_python", "arguments": {"code": f"hou.node({self.node.path()!r}).createNode('null','forbidden')", "description": "拒否確認"}}}
        r.handle(event)
        self.assertFalse(r.transport.replies[-1][1]["success"])
        event["params"]["turnId"] = "current"
        r.interrupt()
        r.handle(event)
        self.assertFalse(r.transport.replies[-1][1]["success"])
        self.assertIsNone(self.node.node("forbidden"))

    def test_steering_failure_keeps_turn_active(self):
        r = Runtime()
        r.transport = FakeTransport()
        r.busy, r.thread_id, r.turn_id = True, "thread", "turn"
        accepted = []
        r.steer("追加指示", lambda: accepted.append(True))
        r.handle({"id": 1, "error": {"message": "stale turn"}})
        self.assertTrue(r.busy)
        self.assertFalse(r.steering)
        self.assertEqual(accepted, [])

    def test_history(self):
        with tempfile.TemporaryDirectory() as directory:
            r = Runtime()
            r.cwd, r.storage, r.thread_id = directory, Path(directory), "saved-thread"
            r.add("user", "日本語の履歴")
            r.save()
            sid = r.session_id
            r.new_chat()
            r.load(sid)
            self.assertTrue(r.resume_needed)
            self.assertEqual(r.thread_id, "saved-thread")
            self.assertEqual(r.messages[0]["text"], "日本語の履歴")

    def test_installed_docs(self):
        response = execute("houdini_docs", {"query": "vellum cloth"})
        self.assertTrue(response["success"], response)
        paths = content(response)["matches"]
        self.assertTrue(paths, response)
        doc = execute("houdini_docs", {"path": paths[0]})
        self.assertTrue(doc["success"], doc)
        self.assertGreater(len(content(doc)["content"]), 30)
        self.assertFalse(execute("houdini_docs", {"path": "../../auth.json"})["success"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
