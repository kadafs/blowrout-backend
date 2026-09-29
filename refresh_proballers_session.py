import sys
import os
import json
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

SESSION_FILE = "data/proballers_session.json"
TARGET_URL = "https://www.proballers.com/basketball/league/118/germany-easycredit-bbl/schedule"

def refresh_session():
    print("=" * 65)
    print("  REFRESHING PROBALLERS CLOUDFLARE SESSION")
    print("=" * 65)
    print("Launching Chrome on your desktop...")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=False,
                channel="chrome",
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized'
                ]
            )
        except Exception:
            # Fallback to standard chromium if channel="chrome" fails
            browser = p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized'
                ]
            )

        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        print(f"Navigating to: {TARGET_URL}")
        try:
            page.goto(TARGET_URL, timeout=30000)
        except Exception as e:
            print(f"Initial navigation notice: {e}")

        print("\n>>> Please click the Cloudflare checkbox in the Chrome window if prompted. <<<")
        print("Waiting for verification to pass...\n")

        # Attempt smart auto-click on Turnstile iframe if present
        time.sleep(2)
        try:
            frame_el = page.locator('iframe[src*="turnstile"], iframe[src*="challenges.cloudflare.com"]').first
            box = frame_el.bounding_box()
            if box:
                page.mouse.move(box['x'] + 28, box['y'] + 32, steps=10)
                time.sleep(0.3)
                page.mouse.down()
                time.sleep(0.1)
                page.mouse.up()
                print("  [+] Attempted automatic Turnstile click...")
        except Exception:
            pass

        max_wait = 90  # 90 seconds timeout
        start = time.time()
        passed = False

        while time.time() - start < max_wait:
            title = page.title()
            if "Just a moment" not in title and title != "":
                print(f"[+] SUCCESS! Cloudflare challenge cleared! Page title: '{title}'")
                passed = True
                break
            time.sleep(1)

        if not passed:
            print("[-] Timed out waiting for Cloudflare challenge.")
            browser.close()
            return False

        # Extract cookies and user agent
        time.sleep(2)
        cookies = context.cookies()
        ua = page.evaluate("navigator.userAgent")
        browser.close()

        cf_clearance = next((c['value'] for c in cookies if c['name'] == 'cf_clearance'), None)

        if not cf_clearance:
            print("[-] Could not find 'cf_clearance' cookie in browser session.")
            return False

        os.makedirs("data", exist_ok=True)
        session_data = {
            "cf_clearance": cf_clearance,
            "user_agent": ua,
            "timestamp": time.time()
        }

        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)

        print(f"\n[+] Saved fresh session to {SESSION_FILE}!")
        print(f"    User-Agent:   {ua}")
        print(f"    cf_clearance: {cf_clearance[:35]}...\n")

        # Test with curl_cffi to verify
        print("Verifying session with fast curl_cffi...")
        try:
            from curl_cffi import requests
            s = requests.Session(impersonate="chrome131")
            s.headers.update({
                "user-agent": ua,
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9",
                "referer": "https://www.proballers.com/",
            })
            s.cookies.set("cf_clearance", cf_clearance, domain=".proballers.com")
            resp = s.get(TARGET_URL, timeout=15)
            if "Just a moment..." not in resp.text:
                print("[+] VERIFIED! curl_cffi passed Cloudflare successfully (HTTP 200).")
                print("You can now run: python scrape_proballers.py --daily today --cutoff_date 2026-09-13\n")
                return True
            else:
                print("[-] Verification failed: Cloudflare still returned challenge.")
                return False
        except Exception as e:
            print(f"[-] Verification check error: {e}")
            return True

if __name__ == "__main__":
    success = refresh_session()
    sys.exit(0 if success else 1)
