@echo off
echo =====================================================
echo   DIANA-WEB v4.0 -- PKTJ Tegal -- LKTI 2026
echo =====================================================
echo.
echo [1] Install dependencies (tunggu sebentar)...
pip install flask flask-sqlalchemy werkzeug pandas openpyxl ultralytics opencv-python --quiet
echo.
echo [2] Menjalankan server...
echo.
echo    Buka browser: http://localhost:5000
echo    Admin : admin / admin123
echo    User  : demo  / demo123
echo.
echo    Tekan Ctrl+C untuk berhenti
echo.
python app_web.py
pause
