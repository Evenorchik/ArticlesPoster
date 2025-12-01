"""
Скрипт для запуска Chrome с remote debugging.
Используйте этот скрипт, если .bat файл не работает.
"""
import subprocess
import time
import sys
import urllib.request
import socket

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT = 9222

def kill_chrome():
    """Закрывает все процессы Chrome."""
    print("Checking for running Chrome processes...")
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "chrome.exe", "/T"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✓ Chrome processes killed")
            time.sleep(2)
        else:
            print("No Chrome processes found (or already closed)")
    except Exception as e:
        print(f"Warning: Could not kill Chrome processes: {e}")

def check_port(port):
    """Проверяет, доступен ли порт."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

def check_debug_endpoint(port):
    """Проверяет, отвечает ли Chrome debug endpoint."""
    try:
        url = f"http://127.0.0.1:{port}/json"
        with urllib.request.urlopen(url, timeout=2) as response:
            data = response.read()
            return len(data) > 0
    except:
        return False

def main():
    print("="*60)
    print("Chrome Remote Debugging Launcher (Python)")
    print("="*60)
    print()
    
    # Шаг 1: Закрываем Chrome
    print("STEP 1: Closing all Chrome windows...")
    kill_chrome()
    print()
    
    # Шаг 2: Проверяем, что порт свободен
    if check_port(DEBUG_PORT):
        print(f"WARNING: Port {DEBUG_PORT} is already in use!")
        print("This might mean Chrome is still running or another app is using this port.")
        response = input("Continue anyway? (y/n): ").strip().lower()
        if response != 'y':
            print("Aborted.")
            return
    print()
    
    # Шаг 3: Запускаем Chrome
    print(f"STEP 2: Starting Chrome with remote debugging on port {DEBUG_PORT}...")
    print(f"Command: {CHROME_PATH} --remote-debugging-port={DEBUG_PORT}")
    print()
    
    try:
        # Запускаем Chrome в отдельном процессе
        process = subprocess.Popen(
            [CHROME_PATH, f"--remote-debugging-port={DEBUG_PORT}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"✓ Chrome process started (PID: {process.pid})")
    except FileNotFoundError:
        print(f"ERROR: Chrome not found at: {CHROME_PATH}")
        print("Please check the path and update CHROME_PATH in this script.")
        return
    except Exception as e:
        print(f"ERROR: Failed to start Chrome: {e}")
        return
    
    # Шаг 4: Ждем и проверяем
    print()
    print("STEP 3: Waiting for Chrome to initialize...")
    for i in range(10):
        time.sleep(1)
        if check_port(DEBUG_PORT):
            print(f"✓ Port {DEBUG_PORT} is now accessible")
            break
        print(f"  Waiting... ({i+1}/10)")
    else:
        print(f"⚠ Port {DEBUG_PORT} is still not accessible after 10 seconds")
        print("Chrome may not have started with remote debugging enabled.")
        return
    
    # Шаг 5: Проверяем debug endpoint
    print()
    print("STEP 4: Verifying Chrome debug endpoint...")
    time.sleep(2)  # Даем Chrome еще немного времени
    if check_debug_endpoint(DEBUG_PORT):
        print("✓ Chrome is in debug mode!")
        print()
        print("="*60)
        print("SUCCESS! Chrome is running with remote debugging.")
        print("="*60)
        print()
        print("You can now run: python medium_poster.py")
        print()
        print("To verify manually, open in Chrome:")
        print(f"  http://localhost:{DEBUG_PORT}")
        print()
        input("Press Enter to exit (Chrome will stay running)...")
    else:
        print("✗ Chrome debug endpoint is not responding")
        print()
        print("TROUBLESHOOTING:")
        print("  1. Check if Chrome window opened")
        print("  2. Try opening manually: http://localhost:9222")
        print("  3. Check Windows Firewall settings")
        print("  4. Try running this script as Administrator")
        print()
        input("Press Enter to exit...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(0)

