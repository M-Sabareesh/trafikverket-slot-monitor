#!/usr/bin/env python3
"""
Session Update Script - Easy way to update GitHub session

This script:
1. Opens a browser window for you to login to Trafikverket
2. Waits for successful login
3. Automatically extracts the session cookies
4. Updates the GitHub secret
5. Triggers the monitoring workflow

Requirements:
    pip install playwright requests
    playwright install chromium

Usage:
    python update_session.py

Environment variables (optional - will prompt if not set):
    GITHUB_TOKEN - GitHub Personal Access Token with 'repo' scope
    GITHUB_REPO - Repository in format 'owner/repo'
"""

import os
import sys
import json
import base64
import time
import getpass
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("❌ Requests not installed. Run: pip install requests")
    sys.exit(1)

try:
    from nacl import public, encoding
except ImportError:
    print("❌ PyNaCl not installed. Run: pip install pynacl")
    sys.exit(1)


def get_env_or_prompt(var_name: str, prompt: str, is_secret: bool = False) -> str:
    """Get environment variable or prompt user."""
    value = os.environ.get(var_name, "").strip()
    if not value:
        if is_secret:
            value = getpass.getpass(prompt)
        else:
            value = input(prompt)
    return value.strip()


def encrypt_secret(public_key: str, secret_value: str) -> str:
    """Encrypt a secret using GitHub's public key."""
    public_key_bytes = base64.b64decode(public_key)
    sealed_box = public.SealedBox(public.PublicKey(public_key_bytes))
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def update_github_secret(token: str, repo: str, secret_name: str, secret_value: str) -> bool:
    """Update a GitHub Actions secret."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Get repository public key
    key_url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
    response = requests.get(key_url, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ Failed to get public key: {response.status_code}")
        print(f"   Response: {response.text}")
        return False
    
    key_data = response.json()
    encrypted_value = encrypt_secret(key_data["key"], secret_value)
    
    # Update secret
    secret_url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
    payload = {
        "encrypted_value": encrypted_value,
        "key_id": key_data["key_id"]
    }
    
    response = requests.put(secret_url, headers=headers, json=payload)
    
    if response.status_code in (201, 204):
        print(f"✅ Secret '{secret_name}' updated successfully")
        return True
    else:
        print(f"❌ Failed to update secret: {response.status_code}")
        print(f"   Response: {response.text}")
        return False


def trigger_workflow(token: str, repo: str, workflow_file: str = "monitor.yml") -> bool:
    """Trigger a GitHub Actions workflow."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/dispatches"
    payload = {"ref": "main"}
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 204:
        print(f"✅ Workflow '{workflow_file}' triggered successfully")
        return True
    else:
        print(f"⚠️  Could not trigger workflow: {response.status_code}")
        return False


def extract_session_from_browser() -> dict | None:
    """Open browser for login and extract session cookies."""
    print("\n🌐 Opening browser for Trafikverket login...")
    print("   Please complete the login process.")
    print("   The browser will close automatically after detecting successful login.\n")
    
    session_data = None
    
    with sync_playwright() as p:
        # Launch browser in non-headless mode so user can interact
        browser = p.chromium.launch(
            headless=False,
            args=['--start-maximized']
        )
        
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = context.new_page()
        
        # Navigate to Trafikverket booking page
        login_url = "https://fp.trafikverket.se/boka/"
        print(f"📍 Navigating to: {login_url}")
        page.goto(login_url)
        
        # Wait for user to complete login
        print("\n⏳ Waiting for login completion...")
        print("   (Looking for 'Mina prov' link or booking elements)\n")
        
        max_wait_time = 300  # 5 minutes
        check_interval = 2  # Check every 2 seconds
        elapsed = 0
        logged_in = False
        
        while elapsed < max_wait_time and not logged_in:
            try:
                # Check for signs of successful login
                # Look for "Mina prov" link or "Boka nytt prov" button
                if page.locator('a:has-text("Mina prov")').count() > 0:
                    logged_in = True
                    print("✅ Detected 'Mina prov' - Login successful!")
                elif page.locator('text="Boka nytt prov"').count() > 0:
                    logged_in = True
                    print("✅ Detected booking page - Login successful!")
                elif page.locator('.logged-in').count() > 0:
                    logged_in = True
                    print("✅ Detected logged-in state!")
                elif "boka" in page.url.lower() and page.locator('a[href*="logout"]').count() > 0:
                    logged_in = True
                    print("✅ Detected logout link - Login successful!")
            except Exception:
                pass
            
            if not logged_in:
                time.sleep(check_interval)
                elapsed += check_interval
                if elapsed % 30 == 0:
                    print(f"   Still waiting... ({elapsed}s elapsed, {max_wait_time - elapsed}s remaining)")
        
        if not logged_in:
            print("❌ Timeout waiting for login. Please try again.")
            browser.close()
            return None
        
        # Extract cookies
        print("\n🍪 Extracting session cookies...")
        cookies = context.cookies()
        
        # Filter for relevant cookies (Trafikverket domain)
        relevant_cookies = [
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c["path"]
            }
            for c in cookies
            if "trafikverket" in c.get("domain", "").lower()
        ]
        
        if relevant_cookies:
            session_data = {"cookies": relevant_cookies}
            print(f"   Found {len(relevant_cookies)} cookies")
        else:
            print("⚠️  No Trafikverket cookies found!")
        
        # Also save localStorage if needed
        try:
            local_storage = page.evaluate("() => Object.entries(localStorage)")
            if local_storage:
                session_data["localStorage"] = dict(local_storage)
                print(f"   Found {len(local_storage)} localStorage items")
        except Exception:
            pass
        
        print("\n🔒 Closing browser...")
        browser.close()
    
    return session_data


def save_session_locally(session_data: dict) -> None:
    """Save session data to local file for backup."""
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)
    
    session_file = data_dir / "session.json"
    with open(session_file, "w") as f:
        json.dump(session_data, f, indent=2)
    
    print(f"💾 Session saved locally to: {session_file}")


def main():
    print("=" * 60)
    print("🚗 Trafikverket Session Update Tool")
    print("=" * 60)
    
    # Get GitHub credentials
    print("\n📋 Configuration")
    print("-" * 40)
    
    github_token = get_env_or_prompt(
        "GITHUB_TOKEN",
        "Enter GitHub Personal Access Token (with 'repo' scope): ",
        is_secret=True
    )
    
    github_repo = get_env_or_prompt(
        "GITHUB_REPO",
        "Enter GitHub repository (e.g., username/repo): "
    )
    
    if not github_token or not github_repo:
        print("❌ GitHub token and repository are required!")
        sys.exit(1)
    
    # Extract session from browser
    session_data = extract_session_from_browser()
    
    if not session_data:
        print("\n❌ Failed to extract session. Please try again.")
        sys.exit(1)
    
    # Encode session data
    session_json = json.dumps(session_data)
    session_base64 = base64.b64encode(session_json.encode()).decode()
    
    print(f"\n📦 Session data size: {len(session_base64)} characters")
    
    # Save locally
    save_session_locally(session_data)
    
    # Update GitHub secret
    print("\n☁️  Updating GitHub Secret...")
    print("-" * 40)
    
    if update_github_secret(github_token, github_repo, "SESSION_DATA", session_base64):
        # Trigger workflow
        print("\n🚀 Triggering monitoring workflow...")
        print("-" * 40)
        trigger_workflow(github_token, github_repo, "monitor.yml")
        
        print("\n" + "=" * 60)
        print("✅ SUCCESS! Session updated and monitoring resumed.")
        print("=" * 60)
        print(f"\n📊 Check workflow status at:")
        print(f"   https://github.com/{github_repo}/actions")
    else:
        print("\n❌ Failed to update GitHub secret.")
        sys.exit(1)


if __name__ == "__main__":
    main()
