import json
from pathlib import Path
import tempfile
import unittest
from build_runtime import backend_names, inventory
from package import verify


class ReleaseTests(unittest.TestCase):
    def test_allowlist_excludes_private_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["core/api.py", "core/access.py", "core/backup.py", "model/baseline.json", "model/user.sqlite3", "core/raw.txt", "translator/test_private.py", "data/private.py"]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic")
            self.assertEqual(backend_names(root), ["core/access.py", "core/api.py", "core/backup.py", "model/baseline.json"])

    def test_inventory_detects_tampering_and_extra_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test.py").write_text("synthetic")
            (root / "manifest.json").write_text(json.dumps({"files": inventory(root)}))
            verify(root)
            (root / "private.sqlite3").write_text("excluded")
            with self.assertRaises(ValueError):
                verify(root)

    def test_escaping_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "escape").symlink_to("/etc/passwd")
            with self.assertRaises(ValueError):
                inventory(root)


if __name__ == "__main__":
    unittest.main()
