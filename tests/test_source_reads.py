"""Real temporary fixtures only. Never read workstation configuration."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lib import xsnapshot as x

class SourceReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.source=self.root/"input"
        self.source.mkdir()
        self.config=self.source/"example.conf"
        self.config.write_text("setting=synthetic\n")
        self.collector=x.Collector(self.root,self.root/"capture",sudo=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_regular_unicode_and_empty_text(self):
        self.config.write_text("theme=é\n",encoding="utf-8")
        self.assertEqual(x.read_config_text(self.config),"theme=é\n")
        self.config.write_bytes(b"")
        self.assertEqual(x.read_config_text(self.config),"")

    def test_final_and_parent_symlinks_never_copy_target_bytes(self):
        link=self.root/"linked.conf"
        link.symlink_to(self.config)
        parent=self.root/"linked-directory"
        parent.symlink_to(self.source,target_is_directory=True)
        for candidate in (link,parent/"example.conf"):
            with self.assertRaises((OSError,ValueError)):
                x.read_config_text(candidate)
            self.assertIsNone(self.collector.copy_file(candidate,"etc/example.conf",follow_symlinks=True))
        self.assertEqual(self.collector.config_index,[])
        self.assertFalse(self.collector.out.exists())
        self.assertNotIn(str(self.config),"\n".join(self.collector.notes))

    def test_hardlinks_directories_and_fifo_are_rejected(self):
        hard=self.root/"hard.conf"
        os.link(self.config,hard)
        fifo=self.root/"pipe"
        os.mkfifo(fifo)
        for candidate in (hard,self.config,self.source,fifo):
            with self.assertRaises((OSError,ValueError)):
                x.read_config_text(candidate)

    def test_size_limit_and_whole_file_binary_guard(self):
        self.config.write_bytes(b"x"*33)
        with self.assertRaisesRegex(ValueError,"size limit"):
            x.read_config_text(self.config,32)
        for raw in (b"x"*8192+b"\x00",b"x"*8192+b"\xff"):
            self.config.write_bytes(raw)
            with self.assertRaises((ValueError,UnicodeError)):
                x.read_config_text(self.config)

    def test_growth_stops_at_limit_plus_one(self):
        self.config.write_bytes(b"x"*16)
        actual_read=os.read
        amounts=[]
        def grow(fd,size):
            if not amounts:
                self.config.write_bytes(b"x"*100)
            amounts.append(size)
            return actual_read(fd,size)
        with patch.object(x.os,"read",side_effect=grow):
            with self.assertRaisesRegex(ValueError,"size limit"):
                x.read_config_text(self.config,32)
        self.assertLessEqual(sum(amounts),33)

    def test_source_directory_swap_cannot_redirect_pinned_file(self):
        target=self.root/"other"
        target.mkdir()
        (target/"example.conf").write_text("OTHER-FIXTURE-MUST-NOT-BE-READ\n")
        actual_open=os.open
        swapped=False
        def swap(path,flags,*args,**kwargs):
            nonlocal swapped
            if str(path).startswith("/proc/self/fd/") and not swapped:
                swapped=True
                self.source.rename(self.root/"original")
                self.source.symlink_to(target,target_is_directory=True)
            return actual_open(path,flags,*args,**kwargs)
        with patch.object(x.os,"open",side_effect=swap):
            self.assertEqual(x.read_config_text(self.config),"setting=synthetic\n")
        self.assertTrue(swapped)

    def test_mutation_during_read_is_not_silently_accepted(self):
        actual_read=os.read
        before=self.config.stat()
        changed=False
        def mutate(fd,size):
            nonlocal changed
            chunk=actual_read(fd,size)
            if not changed:
                changed=True
                self.config.write_text("setting=altered!!\n")
                os.utime(self.config,ns=(before.st_atime_ns,before.st_mtime_ns+1_000_000_000))
            return chunk
        with patch.object(x.os,"read",side_effect=mutate):
            with self.assertRaisesRegex(ValueError,"changed"):
                x.read_config_text(self.config)

    def test_unreadable_source_does_not_escalate_or_echo_diagnostics(self):
        with patch.object(x,"read_config_text",side_effect=PermissionError("PRIVATE-DIAGNOSTIC")), \
             patch.object(self.collector,"sudo_run") as sudo:
            self.assertIsNone(self.collector.copy_file(self.config,"etc/example.conf"))
        sudo.assert_not_called()
        self.assertFalse(hasattr(self.collector,"sudo_read_bytes"))
        self.assertNotIn("PRIVATE-DIAGNOSTIC","\n".join(self.collector.notes))

    def test_linked_tree_is_skipped_and_regular_tree_copies_only_real_files(self):
        linked=self.root/"linked-tree"
        linked.symlink_to(self.source,target_is_directory=True)
        self.assertEqual(self.collector.copy_tree(linked,"applied/test"),0)
        (self.source/"linked.conf").symlink_to(self.config)
        self.assertEqual(self.collector.copy_tree(self.source,"applied/test"),1)
        self.assertEqual(self.collector.config_index[0]["path"],"applied/test/example.conf")

    def test_standard_os_release_alias_has_only_one_fixed_destination(self):
        def read(path):
            if path==Path("/usr/lib/os-release"):
                return 'NAME="Synthetic OS"\n'
            raise ValueError("unapproved link")
        with patch.object(x.os,"readlink",return_value="../usr/lib/os-release"), \
             patch.object(x,"read_config_text",side_effect=read) as reader:
            self.assertIsNotNone(self.collector.copy_file(Path("/etc/os-release"),"etc/os-release",follow_symlinks=True))
            reader.assert_called_once_with(Path("/usr/lib/os-release"))
        with patch.object(x.os,"readlink",return_value="/unrelated/private-file"), \
             patch.object(x,"read_config_text",side_effect=read):
            self.assertIsNone(self.collector.copy_file(Path("/etc/os-release"),"etc/other",follow_symlinks=True))

    def test_tree_entry_limit_stops_traversal(self):
        visited=[]
        def items():
            for index in range(9000):
                visited.append(index)
                yield self.source/str(index)
        with patch.object(Path,"rglob",return_value=items()), \
             patch.object(Path,"is_symlink",return_value=False), \
             patch.object(Path,"is_file",return_value=False):
            self.assertEqual(self.collector.copy_tree(self.source,"applied/test"),0)
        self.assertEqual(len(visited),8193)
        self.assertTrue(any("entry limit" in note for note in self.collector.notes))

    def test_safe_copy_keeps_existing_redaction_hashes_and_private_output(self):
        self.config.write_text("password=synthetic-secret-value\n")
        output=self.collector.copy_file(self.config,"etc/example.conf")
        self.assertIsNotNone(output)
        self.assertNotIn("synthetic-secret-value",output.read_text())
        self.assertEqual(output.stat().st_mode&0o777,0o600)
        self.assertEqual(self.collector.config_index[0]["bytes"],output.stat().st_size)

if __name__=="__main__":
    unittest.main()
