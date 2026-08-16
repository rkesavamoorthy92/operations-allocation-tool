"""PyInstaller entry-point script.

A separate top-level launcher (rather than pointing PyInstaller directly
at ``src/operations_allocation/ui/app.py``) so PyInstaller's module graph
analysis starts from something outside the package -- this avoids any
ambiguity between "run as a script" and "run as part of the
operations_allocation package" that has historically confused
PyInstaller's import scanner for src-layout projects.
"""

from operations_allocation.ui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
