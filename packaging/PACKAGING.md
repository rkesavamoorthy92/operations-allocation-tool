# Packaging: building a standalone .exe

This produces a `--onedir` PyInstaller distribution: a folder containing
`OperationsAllocationTool.exe` plus its dependencies (Python runtime, Qt,
etc.) -- not a single self-extracting file.

Why `--onedir` instead of `--onefile`:

* **Faster startup.** `--onefile` re-extracts everything into a fresh
  temp folder on *every* launch; `--onedir` runs directly from disk.
* **Fewer antivirus/SmartScreen false positives.** Self-extracting
  single-file executables are a much more common malware delivery
  pattern than a plain folder of files, and this is an internal tool
  handed to teammates rather than downloaded from the internet.
* **Easier to debug.** If something breaks on someone's machine, you
  can just look inside the folder rather than guessing what a
  self-extracting archive unpacked.

## Building

```powershell
cd operations-allocation-tool
uv run --frozen pyinstaller packaging/operations_allocation.spec --noconfirm
```

(`--frozen` is currently required -- see the note in the top-level
README about `uv.lock` being stale; without it `uv run` will hang
trying to re-resolve the lockfile over the network instead of just
running pyinstaller.)

Output: `packaging/dist/OperationsAllocationTool/OperationsAllocationTool.exe`
(plus its `_internal/` folder of dependencies -- ship the whole
`OperationsAllocationTool` folder, not just the .exe).

Rebuild takes about 60-90 seconds. Delete `packaging/build/` and
`packaging/dist/` first if you want a fully clean rebuild (stale
PyInstaller caches occasionally cause confusing partial-build issues).

## Distributing to a teammate

Zip the whole `packaging/dist/OperationsAllocationTool/` folder and hand
it over (network share, email, whatever). They unzip it anywhere
writable and double-click `OperationsAllocationTool.exe` -- no Python
installation, no `uv`, nothing else required on their machine.

## Where application data lives (and why this matters for "no rebuild
## needed to add a Program")

`AppContext.default_data_directory()` always resolves to a
**user-writable location outside the installation folder**:

1. `%OPERATIONS_ALLOCATION_DATA_DIR%` if set (see below), else
2. `%LOCALAPPDATA%\OperationsAllocationTool`

This is deliberate and is what makes the "configure a brand new Program
dynamically, without touching code or rebuilding the .exe" requirement
actually true once packaged:

* Every Program's configuration (fields, sampling, allocation, QC
  rules, error rules, email templates -- everything) lives as JSON rows
  in the SQLite database at that location, entirely authored through
  the in-app "Edit Configuration" JSON editor.
* The packaged .exe contains only *code* -- the fixed engines that
  interpret whatever configuration a Program has. It contains **no**
  Program-specific data at all. Adding "Program #7 with a totally
  different column layout and QC rules" tomorrow never requires
  touching this repository, running PyInstaller again, or redistributing
  anything -- just open the app and use "New Program" + "Edit
  Configuration" like normal.
* This also means the .exe is safe to overwrite/upgrade in place later
  (e.g. after a real bug fix) without losing anyone's Programs or Runs --
  the database is never inside the distributed folder.

## Moving to a shared location later (multi-user)

Today's plan is "each person runs their own local copy, own local
database." If/when this needs to become "the whole team sees the same
Programs and Runs," set the `OPERATIONS_ALLOCATION_DATA_DIR` environment
variable (e.g. to a network path) before launching -- no code change or
rebuild required. Two common ways to set it for a packaged .exe:

* A short `.bat` wrapper next to the real .exe:
  ```bat
  @echo off
  set OPERATIONS_ALLOCATION_DATA_DIR=\\some-server\OpsAllocationShared
  start "" "%~dp0OperationsAllocationTool.exe"
  ```
* A desktop shortcut's "Target" set to the same `.bat`, or Windows'
  System Properties > Environment Variables dialog for a per-machine
  default.

Two caveats worth knowing before actually doing this: (1) SQLite is not
designed for concurrent writers over a network share -- fine for a
handful of people who aren't hitting "Freeze"/"Distribute" at the exact
same second, but a real multi-writer bottleneck under heavier load; (2)
whitespace in that env var is stripped automatically (a very easy
mistake via Windows' own environment variable editor), but a typo'd path
will still just silently create a *new*, empty database at the wrong
location rather than erroring loudly -- double check the path.

## What's bundled vs. what isn't

* Bundled: Python runtime, PySide6/Qt, openpyxl, pywin32 -- everything
  needed to run the app with zero prerequisites on the target machine.
* NOT bundled (by design): any Program configuration, any Run data, the
  SQLite database itself, generated artifacts (.xlsx files, JSON
  snapshots). All of that is created fresh, per machine, in the writable
  data directory described above the first time the app runs there.

## Known limitation: Outlook integration requires Outlook

"Send Individual/Consolidated Emails" uses `pywin32`'s COM bridge to
desktop Outlook (`win32com.client`). This only works on a machine with
desktop Outlook installed and configured -- there is no bundled email
sending capability, by design (PROJECT_SPEC.md requires drafting real
Outlook emails, not sending through some other channel). On a machine
without Outlook, `OutlookUnavailableError` surfaces a clear message
rather than crashing; the Run can still proceed since email drafting is
informational, not state-gating.
