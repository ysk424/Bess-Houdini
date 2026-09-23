"""インストーラーの限定編集、バックアップ、冪等性を一時フォルダーで確認。"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
spec = importlib.util.spec_from_file_location("bess_install", ROOT / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
from bess_houdini.rpc import mcp_overrides


class InstallTests(unittest.TestCase):
    def test_dry_run_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            prefs = Path(d)
            hook = prefs / "python3.13libs/uiready.py"
            hook.parent.mkdir()
            original = "import unrelated\nimport houdinimcp  # Auto-start HoudiniMCP server\nother = 42\n"
            hook.write_text(original, encoding="utf-8")
            installer.install(prefs, True, True)
            self.assertFalse((prefs / "packages/bess_houdini.json").exists())
            self.assertEqual(hook.read_text(encoding="utf-8"), original)
            installer.install(prefs, False, True)
            updated = hook.read_text(encoding="utf-8")
            self.assertIn("import unrelated", updated)
            self.assertIn("other = 42", updated)
            self.assertNotIn("import houdinimcp", updated)
            backups = list(hook.parent.glob("*.bess-backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), original)
            installer.install(prefs, False, True)
            self.assertEqual(len(list(hook.parent.glob("*.bess-backup-*"))), 1)

    def test_codex_mcp_override_does_not_quote_cli_key(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            (directory / "config.toml").write_text('[mcp_servers.test_server]\ncommand = "unused"\n', encoding="utf-8")
            with patch.dict("os.environ", {"CODEX_HOME": d}):
                args = mcp_overrides(d)
            self.assertIn("mcp_servers.test_server.enabled=false", args)
            self.assertNotIn('mcp_servers."test_server".enabled=false', args)


if __name__ == "__main__":
    unittest.main(verbosity=2)
