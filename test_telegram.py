#!/usr/bin/env python3
"""
test_telegram.py - Test your Telegram bot credentials for Myth Job Watcher.
"""
import os
import sys
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def load_env(path=".env"):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k not in os.environ and v:
                        os.environ[k] = v

load_env()

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")

SAMPLE_HTML = (
    "🎯 <b>[Myth Job Watcher Test]</b>\n\n"
    "<b>Role:</b> Software Engineer, New Grad\n"
    "<b>Company:</b> Stripe (Greenhouse)\n"
    "<b>Location:</b> Bangalore, India\n"
    "<b>Posted:</b> 21 hrs ago (28 Oct, 02:49 PM IST)\n\n"
    "🔗 <a href='https://stripe.com/jobs/search?gh_jid=8130876'><b>Apply on Career Page</b></a>\n\n"
    "✅ <i>Your Telegram alerts are working perfectly!</i>"
)

def test_telegram():
    print("=== Testing Telegram Bot Configuration ===\n")
    if not (TG_TOKEN and TG_CHAT):
        print("[!] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in environment.\n")
        print("Quick 60-Second Setup:")
        print("1. Open Telegram and search for @BotFather (https://t.me/BotFather).")
        print("2. Send: /newbot and give it a name and username (e.g. AbhijeetJobsBot).")
        print("3. Copy the HTTP API Token it provides.")
        print("4. Start your new bot on Telegram (press 'Start' or send /start).")
        print("5. Open this link in your browser (replace <TOKEN> with your bot token):")
        print("   https://api.telegram.org/bot<TOKEN>/getUpdates")
        print("   Look for \"chat\": {\"id\": 123456789}. That is your Chat ID.\n")
        print("6. In PowerShell, set your variables:")
        print('   $env:TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjk..."')
        print('   $env:TELEGRAM_CHAT_ID="123456789"')
        print("7. Re-run: py test_telegram.py\n")
        return False

    print(f"[*] Sending test alert to Telegram Chat ID: {TG_CHAT}...")
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT,
                "text": SAMPLE_HTML,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if r.status_code == 200:
            print("[+] SUCCESS! Check your Telegram chat - the test alert was delivered.")
            return True
        else:
            print(f"[-] Telegram returned error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[-] Network error: {e}")
    return False

if __name__ == "__main__":
    test_telegram()
