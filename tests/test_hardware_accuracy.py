"""Synthetic command outputs only; no workstation inventory."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from lib import xsnapshot as x

class HardwareAccuracyTest(unittest.TestCase):
    def capture(self, cpu="", memory=""):
        collector=x.Collector(Path("/synthetic-root"),Path("/synthetic-capture"),sudo=False)
        output={"lscpu":cpu,"free -b":memory}
        with patch.object(collector,"run",side_effect=lambda command:output.get(command,"")), \
             patch.object(collector,"sudo_run",return_value=""), \
             patch.object(collector,"write_section"), \
             patch("subprocess.run",side_effect=AssertionError("No real inventory")):
            collector.collect_hardware()
        json.dumps(collector.data,allow_nan=False)
        return collector.data["hardware"]

    def test_missing_output_is_unknown_not_a_specific_machine(self):
        result=self.capture()
        self.assertTrue(all(value=="unknown" for value in result["cpu"].values()))
        self.assertEqual(result["memory"]["total_human"],"unknown")
        for key in ("total_bytes","used_bytes","available_bytes"):
            self.assertIsNone(result["memory"][key])

    def test_partial_cpu_output_does_not_fill_gaps(self):
        cpu=self.capture("Model name: Synthetic CPU\nCPU(s): 8")["cpu"]
        self.assertEqual(cpu["model"],"Synthetic CPU")
        self.assertEqual(cpu["threads"],"8")
        for key in ("sockets","cores","max_mhz","min_mhz","virtualization"):
            self.assertEqual(cpu[key],"unknown")

    def test_reported_cpu_fields_are_retained(self):
        cpu=self.capture("Model name: Synthetic CPU\nCPU(s): 16\nSocket(s): 2\nCore(s) per socket: 4\nCPU max MHz: 4200.25\nCPU min MHz: 800\nVirtualization: VT-x")["cpu"]
        self.assertEqual(cpu["threads"],"16")
        self.assertEqual(cpu["cores"],"4 per socket")
        self.assertEqual(cpu["sockets"],"2")
        self.assertEqual(cpu["max_mhz"],"4200.250")
        self.assertEqual(cpu["min_mhz"],"800.000")
        self.assertEqual(cpu["virtualization"],"VT-x")

    def test_malformed_numeric_output_cannot_crash_or_invent_values(self):
        for value in ("", "N/A", "NaN", "Infinity", "1e999", "-1", "0", "9"*100):
            cpu=self.capture(f"CPU(s): {value}\nCPU max MHz: {value}\nCPU min MHz: {value}")["cpu"]
            for key in ("threads","max_mhz","min_mhz"):
                self.assertEqual(cpu[key],"unknown",value)

    def test_valid_memory_and_zero_usage(self):
        memory=self.capture(memory="Mem: 8589934592 0 0 0 0 6442450944")["memory"]
        self.assertEqual(memory["total_bytes"],8589934592)
        self.assertEqual(memory["total_human"],"8.0 GiB")
        self.assertEqual(memory["used_bytes"],0)
        self.assertEqual(memory["available_bytes"],6442450944)

    def test_invalid_memory_capacity_stays_unknown(self):
        for value in ("-1","0","unknown","NaN","9"*100,"9007199254740992"):
            memory=self.capture(memory=f"Mem: {value} 1 1 1 1 1")["memory"]
            self.assertIsNone(memory["total_bytes"],value)
            self.assertEqual(memory["total_human"],"unknown")

    def test_partial_or_impossible_memory_values_stay_unknown(self):
        self.assertIsNone(self.capture(memory="Mem: 1024 512")["memory"]["total_bytes"])
        memory=self.capture(memory="Mem: 1024 2048 0 0 0 bad")["memory"]
        self.assertEqual(memory["total_bytes"],1024)
        self.assertIsNone(memory["used_bytes"])
        self.assertIsNone(memory["available_bytes"])

if __name__=="__main__":
    unittest.main()
