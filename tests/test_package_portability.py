"""Synthetic native package-manager output only; never query the workstation."""
from pathlib import Path
import unittest
from unittest.mock import patch
from lib import xsnapshot as x


class PackagePortabilityTest(unittest.TestCase):
    def capture(self, tools=(), distro="unknown", outputs=None):
        collector = x.Collector(Path('/synthetic'), Path('/synthetic/capture'), sudo=False)
        collector.data['os'] = {'id': distro}
        outputs = outputs or {}
        writes = {}
        def run(command):
            key = next((key for key in outputs if command.startswith(key)), None)
            code, text = outputs[key] if key else (127, '[unavailable]')
            collector.commands.append({'command': command, 'returncode': code})
            return text
        with patch.object(x.shutil, 'which', side_effect=lambda name: '/synthetic/' + name if name in tools else None), \
             patch.object(collector, 'run', side_effect=run), \
             patch.object(collector, 'write', side_effect=lambda path, text: writes.update({path: text})), \
             patch('subprocess.run', side_effect=AssertionError('No real inventory')):
            collector.collect_packages()
        return collector.data['packages'], writes, collector

    def test_omarchy_uses_pacman_and_retains_versioned_inventory(self):
        data, files, _ = self.capture(['pacman', 'rpm'], 'omarchy', {
            'pacman -Qe': (0, 'zsh 5.9-1\nlinux 6.1-1'),
            'pacman -Qmq': (0, 'local-tool'),
            'pacman -Q': (0, 'zsh 5.9-1\nlinux 6.1-1\nlocal-tool 1.0'),
        })
        self.assertEqual(data['manager'], 'pacman')
        self.assertEqual(data['all_count'], 3)
        self.assertEqual(data['foreign'], ['local-tool'])
        self.assertIn('packages/pacman-all.txt', files)

    def test_ubuntu_filters_removed_packages_and_keeps_manual_versions(self):
        data, files, collector = self.capture(['dpkg-query', 'apt-mark', 'rpm'], 'ubuntu', {
            'dpkg-query': (0, 'installed\tbash\t5.2-1\nconfig-files\tremoved\t1.0\ninstalled\tlibc6:amd64\t2.40'),
            'apt-mark': (0, 'bash\nlibc6\nremoved'),
        })
        self.assertEqual(data['manager'], 'dpkg-query')
        self.assertEqual(data['all'], ['bash 5.2-1', 'libc6:amd64 2.40'])
        self.assertEqual(data['explicit'], data['all'])
        self.assertIsNone(data['foreign'])
        self.assertIsNone(data['foreign_count'])
        self.assertIn('packages/system-all.txt', files)
        self.assertNotIn('pacman', str(collector.commands))

    def test_rpm_inventory_does_not_invent_explicit_or_foreign_packages(self):
        data, _, _ = self.capture(['rpm', 'dpkg-query'], 'fedora', {'rpm': (0, 'bash.x86_64 5.2-1.fc40')})
        self.assertEqual(data['all'], ['bash.x86_64 5.2-1.fc40'])
        self.assertIsNone(data['explicit_count'])
        self.assertIsNone(data['foreign_count'])

    def test_missing_or_failed_manager_is_unknown_not_zero(self):
        for tools, outputs in [((), {}), (['pacman'], {'pacman': (1, 'error')}), (['rpm'], {'rpm': ('timeout', 'partial 1.0')})]:
            data, _, _ = self.capture(tools, outputs=outputs)
            self.assertIsNone(data['all'])
            self.assertIsNone(data['all_count'])

    def test_missing_native_manager_does_not_query_a_foreign_database(self):
        data, _, collector = self.capture(['rpm'], 'ubuntu', {'rpm': (0, '')})
        self.assertEqual(data['manager'], 'unknown')
        self.assertIsNone(data['all_count'])
        self.assertNotIn('rpm', str(collector.commands))

    def test_successful_empty_query_remains_known_empty(self):
        data, _, _ = self.capture(['rpm'], outputs={'rpm': (0, '')})
        self.assertEqual(data['all'], [])
        self.assertEqual(data['all_count'], 0)

    def test_malformed_package_output_does_not_become_inventory(self):
        for output in ['installed\t\t', 'installed\t \t ', 'installed\tbash', 'unstructured diagnostic']:
            data, _, _ = self.capture(['dpkg-query', 'apt-mark'], outputs={'dpkg-query': (0, output), 'apt-mark': (0, '')})
            self.assertIsNone(data['all_count'])
        data, _, _ = self.capture(['rpm'], outputs={'rpm': (0, 'error: broken database')})
        self.assertIsNone(data['all_count'])

    def test_failed_foreign_query_is_not_a_confirmed_empty_list(self):
        data, _, _ = self.capture(['pacman'], outputs={'pacman -Qmq': (1, ''), 'pacman': (0, 'bash 5.2')})
        self.assertEqual(data['all_count'], 1)
        self.assertIsNone(data['foreign_count'])


if __name__ == '__main__':
    unittest.main()
