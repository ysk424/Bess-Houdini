"""Steam版Houdini IndieへBessを登録する。ソースはこのチェックアウトを使用。"""
import argparse
import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def find_houdini(explicit=None):
    candidates = [Path(explicit)] if explicit else []
    if os.environ.get("BESS_HOUDINI_DIR"):
        candidates.append(Path(os.environ["BESS_HOUDINI_DIR"]))
    steam_roots = [Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Steam"]
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam_roots.insert(0, Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
    for steam in list(steam_roots):
        library = steam / "steamapps/libraryfolders.vdf"
        if library.is_file():
            for value in re.findall(r'"path"\s+"([^"]+)"', library.read_text(encoding="utf-8")):
                steam_roots.append(Path(value.replace("\\\\", "\\")))
    candidates.extend(p / "steamapps/common/Houdini Indie" for p in steam_roots)
    for path in candidates:
        if (path / "bin/hython.exe").is_file() and (path / "steam_appid.txt").is_file():
            return path.resolve()
    raise FileNotFoundError("Steam版Houdini Indieが見つかりません。--houdini-dirで指定してください。")


def environment(install):
    code = "import hou,json; print('BESS_ENV='+json.dumps({'version':hou.applicationVersionString(),'prefs':hou.getenv('HOUDINI_USER_PREF_DIR'),'license':str(hou.licenseCategory())}))"
    result = subprocess.run([str(install / "bin/hython.exe"), "-c", code], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=60,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
    for line in result.stdout.splitlines():
        if line.startswith("BESS_ENV="):
            return json.loads(line[9:])
    raise RuntimeError("Houdini環境を確認できませんでした。")


def write_with_backup(path, data, dry_run):
    if path.is_file() and path.read_bytes() == data:
        print("変更なし:", path)
        return
    print("登録:", path)
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(path, path.with_name(path.name + ".bess-backup-" + stamp))
    path.write_bytes(data)


def install(prefs, dry_run=False, disable_legacy=False):
    package = {"load_package_once": True, "version": "0.1.0",
               "env": [{"PYTHONPATH": {"value": (ROOT / "src").as_posix(), "method": "append"}}]}
    write_with_backup(prefs / "packages/bess_houdini.json",
                      (json.dumps(package, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), dry_run)
    for source, destination in [("python_panels/Bess.pypanel", "python_panels/Bess.pypanel"),
                                ("toolbar/bess_houdini.shelf", "toolbar/bess_houdini.shelf")]:
        write_with_backup(prefs / destination, (ROOT / source).read_bytes(), dry_run)
    if disable_legacy:
        for hook in prefs.glob("python*libs/uiready.py"):
            original = hook.read_text(encoding="utf-8")
            updated = re.sub(r"(?m)^import houdinimcp[ \t]*#[ \t]*Auto-start HoudiniMCP server[ \t]*$",
                             "# Bess: HoudiniMCPの自動起動を停止（元のファイルは.bess-backupに保存）", original)
            if updated != original:
                write_with_backup(hook, updated.encode("utf-8"), dry_run)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--houdini-dir")
    parser.add_argument("--prefs-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-legacy-mcp", action="store_true", help="既知のHoudiniMCP自動起動行だけをバックアップして停止")
    args = parser.parse_args()
    location = find_houdini(args.houdini_dir)
    info = environment(location)
    if tuple(int(x) for x in info["version"].split(".")[:2]) < (22, 0):
        raise RuntimeError("この版はHoudini Indie 22以降が対象です。")
    prefs = (args.prefs_dir or Path(info["prefs"])).expanduser().resolve()
    print("Houdini:", location)
    print("Version:", info["version"], info["license"])
    install(prefs, args.dry_run, args.disable_legacy_mcp)
    print("HoudiniのPython PanelでBessを選択してください。初回登録後はHoudiniを再起動してください。")


if __name__ == "__main__":
    main()
