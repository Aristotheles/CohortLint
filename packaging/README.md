# Windows portable package

The Windows package uses PyInstaller's one-file console mode. Build it from a clean
Python 3.12 virtual environment so unrelated packages are not pulled into the executable:

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install "pyinstaller==6.21.0" .
.\.venv-build\Scripts\python.exe -m PyInstaller `
  --noconfirm --clean --onefile --console --name CohortLint `
  --collect-data cohortlint --copy-metadata cohortlint `
  packaging\windows_entry.py
```

Distributions must include the files under `packaging/windows`, the CohortLint MIT
license, and the license notices from every bundled distribution. The executable is a
CLI, so console mode must remain enabled. Build on Windows for Windows; PyInstaller is
not a cross-compiler.
