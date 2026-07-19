@echo off
setlocal
cd /d "%~dp0"
echo CohortLint ornek verileri kontrol ediyor...
"CohortLint.exe" check --config "demo\cohortlint.yaml" --format html --output "demo\report.html" --fail-on never
if errorlevel 1 (
  echo.
  echo Test basarisiz oldu. Hata kodu: %errorlevel%
  pause
  exit /b 1
)
echo.
echo Test basarili. Rapor aciliyor...
start "" "demo\report.html"
pause
