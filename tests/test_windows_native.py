"""Native Windows gates. Inventory remains in temporary local files, never logs/artifacts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lib import windows_inventory as w

@unittest.skipUnless(os.name=='nt' and sys.version_info >= (3,13),'requires native Windows Python 3.13+')
class WindowsNativeTest(unittest.TestCase):
    def test_isolated_preflight(self):
        result=subprocess.run([sys.executable,'-I','-S',w.__file__,'--preflight'],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,'Native prerequisite check failed')
        self.assertTrue(json.loads(result.stdout)['ready'])
    def test_real_cim_query_and_private_capture(self):
        data=w.query_windows()
        self.assertEqual(data['capture_status']['os'],'captured')
        self.assertEqual(data['capture_status']['cpu'],'captured')
        self.assertGreater(data['hardware']['memory']['total_bytes'] or 0,0)
        self.assertGreater(data['hardware']['cpu']['threads'] or 0,0)
        with tempfile.TemporaryDirectory() as tmp:
            root=w.write_capture(data,tmp)
            # Verify actual Windows ACLs, not Unix chmod mode bits.
            quoted=str(root).replace("'","''")
            script=r'''
try {
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$root='ROOT_PATH'
$me=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowed=@($me,'S-1-5-32-544','S-1-5-18')
$paths=@($root)+@(Get-ChildItem -LiteralPath $root -Recurse | ForEach-Object {$_.FullName})
$valid=$true
foreach($path in $paths) {
  $acl=Get-Acl -LiteralPath $path
  $owner=$acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
  $ownerAllowed=$allowed -contains $owner
  if(-not $ownerAllowed) {$valid=$false}
  foreach($entry in $acl.Access) {
    if($entry.AccessControlType -eq 'Allow') {
      $sid=$entry.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
      if($allowed -notcontains $sid -and -not ($sid -eq 'S-1-3-4' -and $ownerAllowed)) {$valid=$false}
    }
  }
}
@{private=$valid; count=$paths.Count} | ConvertTo-Json -Compress
} catch {
  @{error_type=$_.Exception.GetType().FullName; category=$_.CategoryInfo.Category.ToString(); line=$_.InvocationInfo.ScriptLineNumber} | ConvertTo-Json -Compress
  exit 1
}
'''.replace('ROOT_PATH',quoted)
            result=subprocess.run([str(w.powershell_path()),'-NoLogo','-NoProfile','-NonInteractive','-Command',script],capture_output=True,timeout=30)
            report=json.loads(result.stdout.decode('utf-8-sig') or '{}')
            self.assertEqual(result.returncode,0,'Native ACL check failed: '+json.dumps(report))
            self.assertTrue(report['private'],'Capture ACL grants access beyond current user/system/administrators')
            self.assertEqual(report['count'],5)
            snapshot=json.loads((root/'data/snapshot.json').read_text(encoding='utf-8'))
            self.assertEqual(snapshot['host']['hostname'],'this-pc')
            self.assertEqual(snapshot['config_index'],[])

if __name__=='__main__': unittest.main()
