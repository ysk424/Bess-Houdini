"""Codex App Server の標準入出力。Houdini 非依存、認証情報は扱わない。"""
import collections
import glob
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import tomllib


def mcp_overrides(cwd):
    """既存MCPをBessの子プロセスだけで無効化。認証ファイルは扱わない。"""
    paths = [Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"]
    directory = Path(cwd).resolve()
    paths.extend(p / ".codex/config.toml" for p in (directory, *directory.parents))
    names = set()
    for path in paths:
        if path.is_file():
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            names.update(data.get("mcp_servers", {}))
    args = []
    for name in sorted(names):
        # CodexのCLIのドット区切りキーはTOML引用符を解釈しない。
        # 特殊名はruntimeの構造化configでも無効化する。
        if re.fullmatch(r"[A-Za-z0-9_-]+", name):
            args.extend(["-c", "mcp_servers." + name + ".enabled=false"])
    return args


def find_codex(explicit=""):
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file() and path.suffix.lower() == ".exe":
            return str(path)
        raise FileNotFoundError("Codex の実行ファイル（codex.exe）が見つかりません。")
    direct = shutil.which("codex.exe")
    if direct:
        return direct
    roots = set()
    for name in ("codex", "codex.cmd", "codex.ps1"):
        found = shutil.which(name)
        if found:
            roots.add(str(Path(found).parent))
    roots.add(str(Path(os.environ.get("APPDATA", "")) / "npm"))
    for root in sorted(roots):
        for pattern in (
            "node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/*/bin/codex.exe",
            "node_modules/@openai/codex/vendor/*/codex/codex.exe",
            "node_modules/@openai/codex/vendor/*/bin/codex.exe",
        ):
            candidates = glob.glob(str(Path(root) / pattern))
            if candidates:
                return candidates[0]
    raise FileNotFoundError("Codex CLI が見つかりません。設定で codex.exe を指定してください。")


class Transport:
    def __init__(self, executable=""):
        self.executable = find_codex(executable)
        self.events = queue.Queue()
        self.stderr = collections.deque(maxlen=60)
        self.process = None
        self._counter = 0
        self._write_lock = threading.Lock()
        self._closing = False

    def start(self, cwd):
        self.process = subprocess.Popen(
            [self.executable, "app-server", "--stdio", "--disable", "apps",
             "--disable", "plugins", *mcp_overrides(cwd)], cwd=cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", text=True, bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._read, daemon=True, name="Bess・受信").start()
        threading.Thread(target=self._read_errors, daemon=True, name="Bess・診断").start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.events.put(json.loads(line))
                except ValueError:
                    self.stderr.append(line.rstrip()[:2000])
        finally:
            if not self._closing:
                self.events.put({"method": "bess_houdini/disconnected", "params": {}})

    def _read_errors(self):
        for line in self.process.stderr:
            self.stderr.append(line.rstrip()[:2000])

    def send(self, message):
        with self._write_lock:
            if not self.process or self.process.poll() is not None:
                raise ConnectionError("Codex との接続が切れました。再接続してください。")
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()

    def request(self, method, params):
        self._counter += 1
        self.send({"id": self._counter, "method": method, "params": params})
        return self._counter

    def reply(self, request_id, result):
        self.send({"id": request_id, "result": result})

    def close(self):
        self._closing = True
        if self.process:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
