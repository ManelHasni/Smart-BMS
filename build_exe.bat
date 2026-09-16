@echo off
REM ============================================================
REM  Smart BMS -- Script de build .exe (Windows)
REM  A lancer depuis le dossier du projet (ou se trouve main.py)
REM ============================================================

echo.
echo === Smart BMS - Construction de l'executable ===
echo.

REM 1) Verifie que les dependances sont installees
echo Installation/mise a jour de PyInstaller...
python -m pip install --upgrade pyinstaller
if %errorlevel% neq 0 (
    echo [ERREUR] Impossible d'installer/mettre a jour PyInstaller.
    echo Verifiez que Python est bien installe et accessible depuis ce terminal.
    pause
    exit /b 1
)

REM 2) Genere l'icone si elle n'existe pas encore
if not exist "assets\icon.ico" (
    echo Generation de l'icone...
    python assets\generate_icon.py
)

REM 3) Nettoie les anciens builds
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM 4) Lance PyInstaller avec le fichier de configuration
REM    (on utilise "python -m PyInstaller" plutot que la commande "pyinstaller" seule :
REM    si le dossier Scripts de Python n'est pas dans le PATH Windows, la commande directe
REM    echoue avec "n'est pas reconnu..." meme si le paquet est bien installe)
python -m PyInstaller build_exe.spec --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo [ERREUR] La construction a echoue. Voir le detail ci-dessus.
    pause
    exit /b 1
)

echo.
echo === Build termine avec succes ===
echo L'executable se trouve dans : dist\SmartBMS\SmartBMS.exe
echo.
pause
