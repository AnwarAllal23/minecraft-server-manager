@echo off
setlocal

cd /d "%~dp0\.."

if not exist .venv (
    echo Creation de l'environnement virtuel...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

python -m PyInstaller --noconfirm --clean GestionServeursMinecraft.windows.spec

echo.
echo Executable cree: dist\Gestion Serveurs Minecraft\Gestion Serveurs Minecraft.exe
