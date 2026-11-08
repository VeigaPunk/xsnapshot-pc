"""Windows hardware adapter candidate. Standard library only; no upload or config copy.

The query runs only on Windows. Tests use synthetic CIM results. The candidate CLI writes a sealed hardware-only folder. Native Windows
verification is separate from its synthetic tests.
"""
from __future__ import annotations
import argparse
import ctypes
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

MAX_INTEGER = (1 << 53) - 1
CIM_QUERY = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
function Read-Section {
  param([string]$Class, [string[]]$Fields, [string]$Filter = '')
  try {
    $arguments = @{ClassName=$Class; OperationTimeoutSec=15; ErrorAction='Stop'}
    if ($Filter) { $arguments.Filter = $Filter }
    $items = @(Get-CimInstance @arguments | Select-Object -Property $Fields)
    return @{status='captured'; items=$items}
  } catch { return @{status='unavailable'; items=@()} }
}
$result = [ordered]@{
  os = Read-Section 'Win32_OperatingSystem' @('Caption','Version','BuildNumber','OSArchitecture','TotalVisibleMemorySize','FreePhysicalMemory')
  cpu = Read-Section 'Win32_Processor' @('Name','NumberOfCores','NumberOfLogicalProcessors')
  gpu = Read-Section 'Win32_VideoController' @('Name','DriverVersion','CurrentHorizontalResolution','CurrentVerticalResolution','CurrentRefreshRate')
  board = Read-Section 'Win32_BaseBoard' @('Manufacturer','Product','Version')
  disks = Read-Section 'Win32_LogicalDisk' @('DeviceID','Size','FreeSpace','FileSystem') 'DriveType=3'
}
ConvertTo-Json -InputObject $result -Depth 8 -Compress
'''


def number(value, *, positive=False):
    """CIM numerics only; no booleans, lossy JS numbers or non-finite values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 0 <= value <= MAX_INTEGER:
        return None
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        return None
    value = int(value)
    return value if value > 0 or not positive else None


def label(value):
    if not isinstance(value, str):
        return 'unknown'
    value = ''.join(c for c in value.strip() if c.isprintable())[:256]
    return value or 'unknown'


def items(raw, key):
    section = raw.get(key) if isinstance(raw, dict) else None
    if not isinstance(section, dict) or section.get('status') != 'captured':
        return None
    rows = section.get('items')
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return None
    return rows


def sum_field(rows, field):
    if not rows:
        return None
    values = [number(row.get(field), positive=True) for row in rows]
    return number(sum(values), positive=True) if all(v is not None for v in values) else None


def normalize_windows(raw):
    """Map selected fields, dropping every unrecognized field and private identifier."""
    sections = {key: items(raw, key) for key in ('os', 'cpu', 'gpu', 'board', 'disks')}
    os_rows = sections['os'] or []
    system = os_rows[0] if len(os_rows) == 1 else {}
    cpus = sections['cpu'] or []
    boards = sections['board'] or []
    board = boards[0] if len(boards) == 1 else {}
    total_kib = number(system.get('TotalVisibleMemorySize'), positive=True)
    total = number(total_kib * 1024, positive=True) if total_kib is not None else None
    free_kib = number(system.get('FreePhysicalMemory'))
    free = number(free_kib * 1024) if free_kib is not None else None
    if total is None or free is None or free > total:
        free = None
    gpus = [{
        'name': label(row.get('Name')), 'driver': label(row.get('DriverVersion')),
        # Win32_VideoController.AdapterRAM is uint32, not reliable modern VRAM.
        'vram': 'unknown',
    } for row in (sections['gpu'] or [])]
    gpu = gpus[0].copy() if len(gpus) == 1 else {'name':'unknown','driver':'unknown','vram':'unknown'}
    gpu['selection'] = 'single reported adapter' if len(gpus) == 1 else 'not determined'
    disks = []
    for row in sections['disks'] or []:
        size = number(row.get('Size'), positive=True)
        available = number(row.get('FreeSpace'))
        if size is None or available is None or available > size:
            available = None
        # Use drive letters only, never volume labels, serials or device paths.
        name = row.get('DeviceID')
        name = name if isinstance(name, str) and len(name) == 2 and name[0].isascii() and name[0].isalpha() and name[1] == ':' else 'unknown'
        disks.append({'name':name,'size':size,'available_bytes':available,'fstype':label(row.get('FileSystem'))})
    displays = []
    for row in sections['gpu'] or []:
        width = number(row.get('CurrentHorizontalResolution'), positive=True)
        height = number(row.get('CurrentVerticalResolution'), positive=True)
        if width is not None and height is not None:
            displays.append({'width':width,'height':height,'refresh_hz':number(row.get('CurrentRefreshRate'), positive=True)})
    cpu_names = list(dict.fromkeys(label(row.get('Name')) for row in cpus))
    return {
        'host': {'hostname':'this-pc','os':label(system.get('Caption')),'os_id':'windows','architecture':label(system.get('OSArchitecture'))},
        'os': {'name':label(system.get('Caption')),'pretty_name':label(system.get('Caption')),'id':'windows','version':label(system.get('Version')),'build_id':label(system.get('BuildNumber')),'arch':label(system.get('OSArchitecture'))},
        'hardware': {
            'cpu': {'model':'; '.join(cpu_names) or 'unknown','sockets':len(cpus) if cpus else None,'cores':sum_field(cpus,'NumberOfCores'),'threads':sum_field(cpus,'NumberOfLogicalProcessors')},
            'memory': {'total_bytes':total,'total_human':f'{total / (1 << 30):.1f} GiB' if total is not None else 'unknown','free_bytes':free,'source':'OS-visible physical memory'},
            'gpu':gpu,'gpus':gpus,
            'board': {'manufacturer':label(board.get('Manufacturer')),'model':label(board.get('Product')),'version':label(board.get('Version'))},
        },
        'storage': {'disks':disks}, 'desktop': {'monitors':displays},
        'capture_status': {key:'captured' if rows is not None else 'unavailable' for key, rows in sections.items()},
    }


def powershell_path():
    if os.name != 'nt':
        raise RuntimeError('Native Windows collection requires Windows.')
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise RuntimeError('Windows system directory is unavailable.')
    return Path(buffer.value) / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'


def query_windows():
    """Read local CIM using system PowerShell, no profiles, remote host or policy bypass."""
    executable = powershell_path()
    try:
        result = subprocess.run([str(executable),'-NoLogo','-NoProfile','-NonInteractive','-Command',CIM_QUERY],
            capture_output=True, timeout=90, check=False,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0 or len(result.stdout) > 2 * 1024 * 1024:
            raise ValueError('unavailable')
        raw = json.loads(result.stdout.decode('utf-8-sig'))
        if not isinstance(raw, dict):
            raise ValueError('invalid')
        return normalize_windows(raw)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Do not expose stderr, account names, environment paths or raw command output.
        raise RuntimeError('Windows hardware inventory could not be read.') from None


def write_capture(inventory, parent):
    """Create a new private sealed folder. Never reuse or replace an output folder."""
    if os.name == 'nt' and sys.version_info < (3, 13):
        raise RuntimeError('Python 3.13 or newer is required for private Windows output.')
    # Python 3.13+ honors mode 0700 with a current-user/administrators Windows ACL.
    # mkdtemp creates a fresh 0700 directory, avoiding edits to existing ACLs.
    root = Path(tempfile.mkdtemp(prefix='windows-', dir=parent))
    report = (
        '# Windows hardware snapshot\n\n'
        'This capture contains selected local Windows CIM hardware and OS fields. '
        'It is a point-in-time inventory, not a backup or restore image.\n\n'
        'Configuration files, installed applications, network information, user names, '
        'machine names and device serials were not collected. Package lists are unknown, '
        'not empty. GPU VRAM is unknown because the CIM 32-bit field is not a reliable '
        'modern capacity reading. Multiple adapters are listed without choosing one.\n\n'
        'Review data/snapshot.json before sharing. No files were uploaded. The website '
        'needs this complete folder to validate its integrity. Only an explicit publish '
        'sends snapshot JSON; this report remains local.\n'
    ).encode('utf-8')
    data = dict(inventory)
    data.update(schema='xsnapshot/v1', snapshot_id=root.name,
        captured_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        packages={'manager':'not collected', **{key:None for key in ('all','all_count','explicit','explicit_count','foreign','foreign_count')}},
        config_index=[], privacy={'config_files_captured':0,'redactions_applied':0},
        artifacts=[{'path':'REPORT.md','bytes':len(report),'sha256':hashlib.sha256(report).hexdigest()}],
        collector={'name':'xsnapshot-pc','adapter':'windows-cim','status':'candidate'},
        coverage={'configurations':'not collected','applications':'not collected','gpu_vram':'unavailable'})
    bodies = {'REPORT.md':report, 'data/snapshot.json':(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode('utf-8')}
    (root/'data').mkdir(mode=0o700)
    for name, body in bodies.items():
        descriptor = os.open(root/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor,'wb') as output:
            output.write(body)
    seal = ''.join(f'{hashlib.sha256(body).hexdigest()}  {name}\n' for name,body in sorted(bodies.items()))
    descriptor = os.open(root/'ARTIFACTS.sha256',os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8',newline='\n') as output:
        output.write(seal)
    return root


def preflight():
    supported = os.name == 'nt' and sys.version_info >= (3,13)
    isolated = bool(sys.flags.isolated and sys.flags.no_site)
    powershell = powershell_path().is_file() if os.name == 'nt' else False
    return {'ready':supported and isolated and powershell,'windows_python_3_13':supported,
            'isolated_startup':isolated,'system_powershell':powershell,
            'capture_verified':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Windows hardware snapshot candidate; nothing is uploaded.')
    parser.add_argument('--preflight',action='store_true',help='check prerequisites without collecting')
    parser.add_argument('--output-parent',type=Path,help='create a new private capture inside this existing directory')
    args=parser.parse_args(argv)
    try:
        status=preflight()
        if args.preflight:
            print(json.dumps(status)); return 0 if status['ready'] else 2
        if not status['ready']:
            raise RuntimeError('Use Windows Python 3.13+ with -I -S and system Windows PowerShell available.')
        if args.output_parent is None or not args.output_parent.is_dir():
            raise RuntimeError('Choose an existing output parent directory.')
        inventory=query_windows()
        output=write_capture(inventory,args.output_parent)
        print(f'Created local hardware snapshot: {output}')
        print('Review the complete folder before sharing. No upload was made.')
        return 0
    except (OSError,ValueError,RuntimeError):
        print('Capture did not complete. Check prerequisites and output access; any partial folder remains local.',file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
