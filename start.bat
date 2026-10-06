@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 보도자료 쇼츠 메이커

if not exist ".venv\Scripts\python.exe" (
  echo [처음 실행] 설치를 시작합니다. 1~2분 걸립니다...
  python -m venv .venv 2>nul || py -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo Python을 찾을 수 없습니다. Python 설치 시 "Add python.exe to PATH"를 체크했는지 확인하세요.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

where ffmpeg >nul 2>nul || echo [경고] ffmpeg가 없습니다. 영상을 만들려면 "winget install ffmpeg"로 설치하세요.
if exist apikey.txt set /p ANTHROPIC_API_KEY=<apikey.txt

echo.
echo 잠시 후 브라우저가 열립니다: http://localhost:8000
echo 이 창을 닫으면 앱이 꺼집니다.
echo.
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000
pause
