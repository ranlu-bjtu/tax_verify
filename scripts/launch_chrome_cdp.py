"""Helper script to launch Chrome with CDP and keep it running."""
import subprocess, time, sys, os

plugin_path = r"C:\Users\Administrator\Downloads\EtaxPlugin"
user_data_dir = os.path.abspath(r"./browser_profile/etax_cdp_final")
os.makedirs(user_data_dir, exist_ok=True)

chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
cmd = [
    chrome_path,
    "--remote-debugging-port=9222",
    "--load-extension=" + plugin_path,
    "--user-data-dir=" + user_data_dir,
    "--no-first-run",
    "--no-default-browser-check",
    "https://login.chanjet.com/",
]

print("Launching Chrome...")
proc = subprocess.Popen(cmd)
time.sleep(5)

# Verify CDP
import urllib.request
try:
    resp = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5)
    print("CDP port 9222 is active!")
    print(resp.read().decode()[:200])
except:
    print("CDP port 9222 NOT active. Chrome may have merged with existing instance.")
    print("Please close ALL Chrome windows first, then run this script again.")
    sys.exit(1)

print("\nChrome is running with CDP on port 9222.")
print("Please login to Chanjet in the Chrome window.")
print("After login, press Enter to continue...")
sys.stdin.readline()

# Keep Chrome alive until user exits
print("Chrome process still running. Press Enter to exit this script (Chrome stays open).")
sys.stdin.readline()