@echo off
REM ============================================================
REM  Smart BMS -- Lance la suite de tests + rapport de couverture
REM  A lancer depuis le dossier du projet (ou se trouve main.py)
REM ============================================================

echo.
echo === Smart BMS - Tests automatises ===
echo.

python -m pip install --upgrade pytest pytest-cov >nul 2>&1

echo Lancement des tests avec couverture de code...
echo.
python -m pytest tests\ --cov=. --cov-report=html --cov-report=term-missing --cov-config=.coveragerc

if %errorlevel% neq 0 (
    echo.
    echo [ATTENTION] Certains tests ont echoue. Voir le detail ci-dessus.
    pause
    exit /b 1
)

echo.
echo === Tous les tests sont passes ===
echo Rapport de couverture HTML : htmlcov\index.html
echo.

set /p OPEN="Ouvrir le rapport de couverture maintenant ? (o/n) : "
if /i "%OPEN%"=="o" start htmlcov\index.html

pause
