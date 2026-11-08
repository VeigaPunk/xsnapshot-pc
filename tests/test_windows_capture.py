"""Temporary synthetic capture only, never actual hardware inventory."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lib import windows_inventory as w
from test_windows_inventory import fixture

class WindowsCaptureTest(unittest.TestCase):
    def test_seal_and_schema_cover_exactly_the_created_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=w.write_capture(w.normalize_windows(fixture()),tmp)
            data=json.loads((root/'data/snapshot.json').read_text())
            self.assertEqual(data['snapshot_id'],root.name)
            self.assertEqual(data['schema'],'xsnapshot/v1')
            self.assertEqual(data['config_index'],[])
            self.assertIsNone(data['packages']['all'])
            self.assertEqual(data['hardware']['board']['model'],'Board')
            seal=dict(line.split('  ',1)[::-1] for line in (root/'ARTIFACTS.sha256').read_text().splitlines())
            self.assertEqual(set(seal),{'REPORT.md','data/snapshot.json'})
            for name,digest in seal.items():
                self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)
            self.assertEqual(data['artifacts'][0]['sha256'],seal['REPORT.md'])
    def test_repeat_creates_a_new_folder_without_touching_the_old_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory=w.normalize_windows(fixture())
            one=w.write_capture(inventory,tmp)
            before=(one/'data/snapshot.json').read_bytes()
            two=w.write_capture(inventory,tmp)
            self.assertNotEqual(one,two)
            self.assertEqual((one/'data/snapshot.json').read_bytes(),before)
    @unittest.skipIf(os.name=='nt','Unix mode assertions, Windows ACL needs native verification')
    def test_output_is_private_despite_a_permissive_umask(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=os.umask(0)
            try: root=w.write_capture(w.normalize_windows(fixture()),tmp)
            finally: os.umask(old)
            for path in [root,*root.rglob('*')]:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o700 if path.is_dir() else 0o600)
    def test_cli_preflight_does_not_query_or_write(self):
        with patch.object(w,'preflight',return_value={'ready':True}),patch.object(w,'query_windows',side_effect=AssertionError('No inventory')),patch.object(w,'write_capture',side_effect=AssertionError('No capture')),patch('builtins.print'):
            self.assertEqual(w.main(['--preflight']),0)

if __name__=='__main__': unittest.main()
