"""Synthetic Windows CIM fixtures only. No host capture."""
import copy
import json
import math
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import windows_inventory as w


def fixture():
    return {key:{'status':'captured','items':value} for key,value in {
        'os':[{'Caption':'Windows Synthetic','Version':'10.0','BuildNumber':'26100','OSArchitecture':'64-bit','TotalVisibleMemorySize':16777216,'FreePhysicalMemory':4194304}],
        'cpu':[{'Name':'Synthetic CPU','NumberOfCores':8,'NumberOfLogicalProcessors':16}],
        'gpu':[{'Name':'Synthetic GPU','DriverVersion':'1.2.3','CurrentHorizontalResolution':1920,'CurrentVerticalResolution':1080,'CurrentRefreshRate':60}],
        'board':[{'Manufacturer':'Synthetic','Product':'Board','Version':'1'}],
        'disks':[{'DeviceID':'C:','Size':500000000000,'FreeSpace':200000000000,'FileSystem':'NTFS'}],
    }.items()}

class WindowsInventoryTest(unittest.TestCase):
    def test_selected_fields_and_units(self):
        raw=fixture(); before=copy.deepcopy(raw); data=w.normalize_windows(raw)
        self.assertEqual(data['hardware']['cpu']['cores'],8)
        self.assertEqual(data['hardware']['memory']['total_bytes'],16 << 30)
        self.assertEqual(data['hardware']['memory']['free_bytes'],4 << 30)
        self.assertEqual(data['storage']['disks'][0]['available_bytes'],200000000000)
        self.assertEqual(data['desktop']['monitors'][0]['width'],1920)
        self.assertEqual(raw,before)
        json.dumps(data,allow_nan=False)
    def test_no_private_ids_or_inferred_vram(self):
        raw=fixture()
        for section in raw.values():
            for row in section['items']:
                row.update(SerialNumber='private-serial',UserName='private-user',CSName='private-host',PNPDeviceID='private-device',AdapterRAM=4293918720)
        encoded=json.dumps(w.normalize_windows(raw))
        self.assertNotIn('private-',encoded)
        self.assertEqual(w.normalize_windows(raw)['hardware']['gpu']['vram'],'unknown')
        for field in ('SerialNumber','UserName','CSName','PNPDeviceID','AdapterRAM','ComputerName','ExecutionPolicy'):
            self.assertNotIn(field,w.CIM_QUERY)
    def test_missing_or_failed_sections_are_not_confirmed_empty(self):
        for raw in ({},None,{'gpu':{'status':'unavailable','items':[{'Name':'ignored'}]}}):
            data=w.normalize_windows(raw)
            self.assertEqual(data['capture_status']['gpu'],'unavailable')
            self.assertEqual(data['hardware']['gpu']['name'],'unknown')
            self.assertIsNone(data['hardware']['memory']['total_bytes'])
        self.assertEqual(w.normalize_windows({'gpu':{'status':'captured','items':[]}})['capture_status']['gpu'],'captured')
    def test_multiple_gpus_are_not_added_or_selected(self):
        raw=fixture();raw['gpu']['items'].append({'Name':'Another GPU'})
        data=w.normalize_windows(raw)
        self.assertEqual(len(data['hardware']['gpus']),2)
        self.assertEqual(data['hardware']['gpu']['name'],'unknown')
        self.assertEqual(data['hardware']['gpu']['selection'],'not determined')
    def test_multiple_cpus_sum_only_reported_counts(self):
        raw=fixture();raw['cpu']['items']*=2
        data=w.normalize_windows(raw)
        self.assertEqual(data['hardware']['cpu']['cores'],16)
        raw['cpu']['items'][1]={'Name':'Other CPU'}
        self.assertIsNone(w.normalize_windows(raw)['hardware']['cpu']['cores'])
    def test_invalid_numeric_values_do_not_crash(self):
        for value in (True,'16',-1,math.nan,math.inf,1.5,1 << 53,10**1000,None):
            self.assertIsNone(w.number(value))
        self.assertEqual(w.number(0),0)
        self.assertIsNone(w.number(0,positive=True))
    def test_impossible_free_memory_and_capacity_stay_unknown(self):
        raw=fixture();raw['os']['items'][0]['FreePhysicalMemory']=1 << 45
        raw['disks']['items'][0]['FreeSpace']=1 << 45
        data=w.normalize_windows(raw)
        self.assertIsNone(data['hardware']['memory']['free_bytes'])
        self.assertIsNone(data['storage']['disks'][0]['available_bytes'])
    @unittest.skipIf(os.name=='nt','non-Windows guard')
    def test_non_windows_does_not_launch_powershell(self):
        with patch.object(w.subprocess,'run',side_effect=AssertionError('No actual query')):
            with self.assertRaisesRegex(RuntimeError,'requires Windows'):
                w.query_windows()
    def test_query_uses_fixed_flags_and_returns_only_normalized_fields(self):
        raw=fixture()
        with patch.object(w,'powershell_path',return_value=Path('/synthetic/powershell.exe')),patch.object(w.subprocess,'run') as run:
            run.return_value.returncode=0;run.return_value.stdout=json.dumps(raw).encode()
            self.assertEqual(w.query_windows()['host']['hostname'],'this-pc')
            args,kwargs=run.call_args
            self.assertEqual(args[0][1:5],['-NoLogo','-NoProfile','-NonInteractive','-Command'])
            self.assertEqual(kwargs['timeout'],90)
            self.assertNotIn('shell',kwargs)
    def test_query_errors_do_not_expose_stderr_or_paths(self):
        with patch.object(w,'powershell_path',return_value=Path('/synthetic/powershell.exe')),patch.object(w.subprocess,'run') as run:
            run.return_value.returncode=1;run.return_value.stdout=b'';run.return_value.stderr=b'private-account-path'
            with self.assertRaisesRegex(RuntimeError,'^Windows hardware inventory could not be read\\.$'):
                w.query_windows()

if __name__=='__main__': unittest.main()
