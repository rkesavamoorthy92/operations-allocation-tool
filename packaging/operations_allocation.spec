# PyInstaller build spec for the Operations Allocation Tool.
#
# Produces a --onedir distribution (a folder, not a single .exe) --
# chosen deliberately over --onefile:
#   * Faster startup (no self-extraction to a temp folder on every launch).
#   * --onefile's self-extracting binaries are more frequently flagged by
#     antivirus/Windows Defender SmartScreen on corporate machines than a
#     plain folder of files, which matters for an internal offline tool
#     handed to teammates rather than downloaded from the internet.
#   * Easier to inspect/diff when something goes wrong on someone's
#     machine (you can just look at what's in the folder).
#
# Build with:  uv run pyinstaller packaging/operations_allocation.spec
# Output:      dist/OperationsAllocationTool/OperationsAllocationTool.exe
#
# Deliberately does NOT use collect_all("PySide6") -- that sweeps in
# every PySide6 submodule (QtWebEngine, Qt3D, Bluetooth, ...), none of
# which this app imports, and turns a ~30 second build into a
# multi-minute one producing a multi-GB folder. This app only ever
# imports QtWidgets/QtGui/QtCore (see `grep -r "from PySide6"`), and
# PyInstaller's own bundled hook-PySide6*.py hooks already handle those
# correctly by tracing actual imports -- no manual collection needed.
#
# IMPORTANT: this only bundles the *application*. Program/Run data is
# never bundled -- AppContext.default_data_directory() always resolves to
# a writable per-user (or OPERATIONS_ALLOCATION_DATA_DIR-overridden)
# location at runtime, never anything inside this build output. That is
# precisely what makes "configure a new Program without rebuilding the
# exe" possible: Program configuration lives in that external SQLite
# database, not in anything PyInstaller freezes.

a = Analysis(
    ["run_app.py"],
    pathex=["../src"],
    binaries=[],
    datas=[],
    hiddenimports=["win32timezone"],  # commonly needed transitively by pywin32/Outlook COM, not always auto-detected.
    hookspath=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OperationsAllocationTool",
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="OperationsAllocationTool",
)
