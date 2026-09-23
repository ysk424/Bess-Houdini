"""Houdini 同梱ヘルプのパス検索・本文取得。ネットワークもMCPも不要。"""
from functools import lru_cache
from pathlib import Path
import re
import zipfile


@lru_cache(maxsize=2)
def catalog(root):
    entries = {}
    directory = Path(root)
    for archive in sorted(directory.glob("*.zip")):
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if name.endswith((".txt", ".html", ".md")):
                    key = name if name.startswith(archive.stem + "/") else archive.stem + "/" + name
                    entries.setdefault(key, (str(archive), name))
    for path in directory.glob("*.txt"):
        entries[path.name] = (str(path), None)
    return entries


def lookup(root, query="", path="", limit=6):
    entries = catalog(str(root))
    if path:
        if path not in entries:
            raise ValueError("ヘルプのパスが見つかりません。先に query で検索してください。")
        file, member = entries[path]
        if member:
            with zipfile.ZipFile(file) as archive:
                with archive.open(member) as stream:
                    content = stream.read(100000).decode("utf-8", errors="replace")
        else:
            content = Path(file).read_text(encoding="utf-8", errors="replace")[:100000]
        return {"path": path, "content": content[:30000], "truncated": len(content) > 30000}
    terms = re.findall(r"[a-z0-9_]+", query.lower())
    if not terms:
        raise ValueError("英語のノード名やAPI名を指定してください（例: vellum cloth、hou Node）。")
    ranked = []
    for key in entries:
        lower = key.lower()
        score = sum(1 for term in terms if term in lower)
        if score:
            ranked.append((score, key))
    ranked.sort(key=lambda x: (-x[0], len(x[1]), x[1]))
    return {"query": query, "matches": [k for _, k in ranked[:max(1, min(int(limit), 12))]],
            "note": "同梱ヘルプのパス検索。本文は path を指定して取得。英語名で検索。"}
