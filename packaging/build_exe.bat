@echo off
rem Gera dist\AntigravityGate.exe neste computador (alternativa a baixar o .exe pronto do GitHub).
rem Uso: coloque este arquivo na mesma pasta do AntigravityGate.py e dê duplo clique.
cd /d "%~dp0"
if not exist AntigravityGate.py (
  echo Nao achei AntigravityGate.py nesta pasta. Copie este .bat para a pasta do AntigravityGate.py.
  pause & exit /b 1
)
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% --version || (echo Python nao encontrado. & pause & exit /b 1)
%PY% -m pip install --upgrade pip pyinstaller || (echo Falha ao instalar o PyInstaller. & pause & exit /b 1)
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name AntigravityGate AntigravityGate.py || (echo Falha ao gerar o .exe. & pause & exit /b 1)
echo.
echo Pronto: %cd%\dist\AntigravityGate.exe
pause
