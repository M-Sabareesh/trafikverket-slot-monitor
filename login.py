#!/usr/bin/env python3
"""
Simple Login Script for Trafikverket Monitor

This script:
1. Opens a browser for BankID login
2. Saves the session locally
3. Updates the GitHub SESSION_DATA secret

Usage:
    python login.py
"""

import asyncio
import base64
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from playwright.async_api import async_playwright


DATA_DIR = Path(__file__).parent / "data"
SESSION_FILE = DATA_DIR / "session.json"
REPO = "M-Sabareesh/trafikverket-slot-monitor"
BASE_URL = "https://fp.trafikverket.se/Boka/"


async def login():
    """Open browser, wait for login, save session."""
    
    print("=" * 60)
    print("🔐 TRAFIKVERKET LOGIN")
    print("=" * 60)
    print()
    
    # Ensure data directory exists
    DATA_DIR.mkdir(exist_ok=True)
    
    async with async_playwright() as p:
        print("🌐 Launching browser...")
        browser = await p.chromium.launch(
            headless=False,
            args=['--no-sandbox', '--disable-setuid-sandbox'],
            slow_mo=100
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()
        
        print(f"📍 Navigating to {BASE_URL}...")
        await page.goto(BASE_URL, wait_until='networkidle', timeout=60000)
        
        print()
        print("=" * 60)
        print("📱 Please complete BankID login in the browser window")
        print("   The script will automatically detect when you're logged in")
        print("=" * 60)
        print()
        
        # Wait for login - check for logged-in indicators
        logged_in = False
        timeout = 180  # 3 minutes
        start_time = asyncio.get_event_loop().time()
        
        while not logged_in and (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                # Check for logged-in indicators
                indicators = [
                    'button:has-text("Logga ut")',
                    'a:has-text("Logga ut")',
                    'text="Vad vill du boka?"',
                    '#licence-type-select',
                ]
                
                for selector in indicators:
                    try:
                        elem = page.locator(selector)
                        if await elem.count() > 0 and await elem.first.is_visible():
                            logged_in = True
                            print(f"✅ Detected login success: {selector}")
                            break
                    except:
                        continue
                
                if not logged_in:
                    await asyncio.sleep(2)
                    elapsed = int(asyncio.get_event_loop().time() - start_time)
                    if elapsed % 10 == 0 and elapsed > 0:
                        print(f"   ⏳ Waiting for login... ({elapsed}s)")
                        
            except Exception as e:
                print(f"   Check error: {e}")
                await asyncio.sleep(2)
        
        if not logged_in:
            print("❌ Login timed out after 3 minutes")
            await browser.close()
            return False
        
        print()
        print("✅ Login successful!")
        print("⏳ Waiting for cookies to be set...")
        await asyncio.sleep(5)
        
        # Navigate to capture all cookies
        print("🔄 Navigating to capture session cookies...")
        await page.goto(BASE_URL + "#/search", wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)
        
        # Save session
        print(f"💾 Saving session to {SESSION_FILE}...")
        await context.storage_state(path=str(SESSION_FILE))
        
        # Verify session was saved
        with open(SESSION_FILE, 'r') as f:
            session = json.load(f)
        
        cookies = session.get('cookies', [])
        print(f"   Saved {len(cookies)} cookies")
        
        # Check LoginValid
        for cookie in cookies:
            if cookie.get('name') == 'LoginValid':
                login_valid = cookie.get('value')
                print(f"   LoginValid: {login_valid}")
                try:
                    expiry = datetime.strptime(login_valid, "%Y-%m-%d %H:%M")
                    remaining = (expiry - datetime.now()).total_seconds() / 60
                    print(f"   Session valid for {int(remaining)} minutes")
                except:
                    pass
                break
        
        await browser.close()
        
    return True


def update_github_secret():
    """Update the GitHub SESSION_DATA secret."""
    
    print()
    print("=" * 60)
    print("☁️  UPDATING GITHUB SECRET")
    print("=" * 60)
    print()
    
    if not SESSION_FILE.exists():
        print("❌ No session file found!")
        return False
    
    # Read and encode session
    with open(SESSION_FILE, 'r') as f:
        session_data = f.read()
    
    session_b64 = base64.b64encode(session_data.encode()).decode()
    print(f"📦 Encoded session: {len(session_b64)} characters")
    
    # Check for gh CLI
    try:
        subprocess.run(['gh', '--version'], capture_output=True, check=True)
    except FileNotFoundError:
        print("❌ GitHub CLI (gh) not found!")
        print("   Install: https://cli.github.com/")
        return False
    
    # Check authentication
    result = subprocess.run(['gh', 'auth', 'status'], capture_output=True, text=True)
    if result.returncode != 0:
        print("❌ Not logged in to GitHub CLI!")
        print("   Run: gh auth login")
        return False
    
    # Update secret
    print(f"🔄 Updating SESSION_DATA secret in {REPO}...")
    result = subprocess.run(
        ['gh', 'secret', 'set', 'SESSION_DATA', '--repo', REPO],
        input=session_b64,
        text=True,
        capture_output=True
    )
    
    if result.returncode == 0:
        print("✅ SESSION_DATA secret updated successfully!")
        return True
    else:
        print(f"❌ Failed to update secret: {result.stderr}")
        return False


def trigger_workflow():
    """Trigger a test workflow run."""
    
    print()
    print("🚀 Triggering test workflow...")
    
    result = subprocess.run(
        ['gh', 'workflow', 'run', 'monitor.yml', '--repo', REPO],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("✅ Workflow triggered!")
        print(f"   Check: https://github.com/{REPO}/actions")
    else:
        print(f"⚠️  Could not trigger workflow: {result.stderr}")


def main():
    print()
    print("🚗 TRAFIKVERKET SESSION MANAGER")
    print()
    
    # Step 1: Login
    success = asyncio.run(login())
    
    if not success:
        print()
        print("❌ Login failed. Please try again.")
        sys.exit(1)
    
    # Step 2: Update GitHub secret
    if not update_github_secret():
        print()
        print("❌ Failed to update GitHub secret.")
        sys.exit(1)
    
    # Step 3: Trigger test workflow
    trigger_workflow()
    
    print()
    print("=" * 60)
    print("✅ ALL DONE!")
    print("=" * 60)
    print()
    print("Your session has been saved and uploaded to GitHub.")
    print("The cron-job.org trigger will now use this session.")
    print()
    print("The session will be automatically refreshed each time")
    print("the monitor runs successfully.")
    print()
    print(f"📊 Monitor status: https://github.com/{REPO}/actions")
    print()


if __name__ == "__main__":
    main()
