# Windows hardware candidate

This dependency-free Python candidate captures selected OS, CPU, memory, GPU, motherboard and fixed-drive fields through local Windows CIM. It is an initial hardware-only path, not parity with the Linux configuration collector. Applications, configuration files, network details, machine/user names and device serials are not collected. Unavailable readings stay unknown. CIM GPU memory is not used because its 32-bit field cannot reliably represent modern VRAM.

## Run from reviewed source

Use Windows Python 3.13 or newer. From the source folder, check prerequisites without collecting:

```powershell
python -I -S lib/windows_inventory.py --preflight
```

Then choose an existing local output directory, for example your home folder:

```powershell
python -I -S lib/windows_inventory.py --output-parent "$HOME"
```

This creates a fresh private `windows-*` folder with `data/snapshot.json`, `REPORT.md` and `ARTIFACTS.sha256`. It never replaces an existing capture or uploads anything. Review the output and open the complete folder on the website. Publication is a separate action. The matching null-package importer is in website PR #26; the shared collector validator changes are in collector PR #6.

Python 3.13 is required because its Windows directory creation applies a current-user/administrator ACL for mode 0700. These are local access controls, not encryption or protection against administrators/the same account. No execution-policy change or elevated privileges are requested. Interrupted output may leave a partial private folder; do not publish it.

## Verification boundary

Synthetic unit tests and a local synthetic collector-validation → website-import → in-memory publish/view/delete integration have passed on Linux. The Windows workflow exercises actual CIM and filesystem ACLs on a Windows GitHub runner; inspect that exact branch's result before treating native execution as verified. That runner is not a test on a physical gaming PC or the user's machine. The tests retain runner inventory only in temporary local directories, do not upload it, and log only checks/pass/fail. No real Windows support claim should be made until that gate passes.

Sources:
- [Python directory mode and Windows access controls](https://docs.python.org/3/library/os.html#os.mkdir)
- [Python 3.13 temporary-directory change](https://docs.python.org/3/whatsnew/3.13.html)
- [Microsoft Win32_VideoController, including AdapterRAM](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-videocontroller)
- [Microsoft local CIM queries](https://learn.microsoft.com/en-us/powershell/scripting/samples/getting-wmi-objects--get-ciminstance-)

## Local Windows check, 8 November 2026

The same selected-field CIM query ran successfully on a connected Windows PC with Python 3.13.15: OS, CPU, GPU, motherboard and disk sections returned, and memory/thread validity checks passed. A separate synthetic directory/file check verified the Windows ACL primitive, including OWNER RIGHTS only when its owner is allowed. Real inventory was not saved or uploaded. The full Python candidate suite has not run on that PC because the supported file-transfer helper failed on Windows extended attributes. These component checks do not establish full native capture support.
