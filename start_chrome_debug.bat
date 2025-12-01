@echo off
echo ========================================
echo Chrome Remote Debugging Launcher
echo ========================================
echo.
echo STEP 1: Checking if Chrome is running...
tasklist /FI "IMAGENAME eq chrome.exe" 2>NUL | find /I /N "chrome.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo WARNING: Chrome is already running!
    echo Please close ALL Chrome windows first.
    echo.
    echo Killing Chrome processes...
    taskkill /F /IM chrome.exe /T >NUL 2>&1
    timeout /t 3 /nobreak >NUL
    echo Chrome processes killed. Waiting 2 seconds...
    timeout /t 2 /nobreak >NUL
)

echo.
echo STEP 2: Starting Chrome with remote debugging...
echo Command: chrome.exe --remote-debugging-port=9222
echo.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

echo Chrome is starting...
echo Waiting 5 seconds for Chrome to load...
timeout /t 5 /nobreak >NUL

echo.
echo STEP 3: Verifying remote debugging...
echo Opening http://localhost:9222 in default browser to verify...
start http://localhost:9222

echo.
echo ========================================
echo If you see JSON data in the browser, Chrome is in debug mode!
echo If you see "This site cannot be reached", Chrome is NOT in debug mode.
echo ========================================
echo.
echo You can now run: python medium_poster.py
echo.
pause

