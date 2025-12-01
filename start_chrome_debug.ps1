# PowerShell script to start Chrome with remote debugging
Write-Host "Starting Chrome with remote debugging..." -ForegroundColor Green
Write-Host ""
Write-Host "Make sure all Chrome windows are closed first!" -ForegroundColor Yellow
Write-Host ""
Read-Host "Press Enter to continue"

& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

Write-Host ""
Write-Host "Chrome started with remote debugging on port 9222" -ForegroundColor Green
Write-Host "You can now run medium_poster.py" -ForegroundColor Green

