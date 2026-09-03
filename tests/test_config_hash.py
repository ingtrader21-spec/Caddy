from pathlib import Path
import tempfile,unittest
from scripts.hash_config_tree import config_tree_hash
class ConfigHashTests(unittest.TestCase):
    def test_hash_is_stable_and_excludes_private_material(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'sites').mkdir(); (root/'sites/a.caddy').write_text('a'); first=config_tree_hash(root); (root/'private').mkdir(); (root/'private/key.pem').write_text('secret'); self.assertEqual(first,config_tree_hash(root)); (root/'sites/a.caddy').write_text('b'); self.assertNotEqual(first,config_tree_hash(root))
if __name__=='__main__': unittest.main()
