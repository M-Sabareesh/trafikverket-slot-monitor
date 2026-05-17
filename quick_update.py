#!/usr/bin/env python3
"""
Quick Session Update - Run this after logging in locally

Usage:
    1. First login: python main.py --login
    2. Then run this: python quick_update.py
    
This will take your local session and push it to GitHub.
"""

import os
import sys
import json
import base64
import subprocess
from pathlib import Path

def main():
    print("=" * 60)
    print("🚀 Quick Session Update to GitHub")
    print("=" * 60)
    
    # Check for session file
    session_file = Path("data/session.json")
    if not session_file.exists():
        print("\n❌ No session.json found!")
        print("\n📝 First, run this command to login:")
        print("   cd src && python main.py --login")
        print("\nThen run this script again.")
        sys.exit(1)
    
    # Load and validate session
    with open(session_file) as f:
        session = json.load(f)
    
    cookies = session.get("cookies", [])
    print(f"\n✅ Found session with {len(cookies)} cookies")
    
    # Check for httpOnly cookies (important ones)
    http_only = [c for c in cookies if c.get("httpOnly")]
    if not http_only:
        print("⚠️  Warning: No httpOnly cookies found - session may be incomplete")
    else:
        print(f"   Including {len(http_only)} httpOnly cookies (good!)")
    
    # Encode session
    session_json = json.dumps(session)
    session_b64 = base64.b64encode(session_json.encode()).decode()
    print(f"\n📦 Encoded session: {len(session_b64)} characters")
    
    # Get GitHub repo
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True
        )
        remote_url = result.stdout.strip()
        # Extract owner/repo from URL
        if "github.com" in remote_url:
            if remote_url.startswith("git@"):
                # git@github.com:owner/repo.git
                repo = remote_url.split(":")[-1].replace(".git", "")
            else:
                # https://github.com/owner/repo.git
                repo = "/".join(remote_url.split("/")[-2:]).replace(".git", "")
            print(f"📂 Repository: {repo}")
        else:
            repo = None
    except:
        repo = None
    
    if not repo:
        repo = input("Enter GitHub repo (owner/repo): ").strip()
    
    # Check for GitHub CLI
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
        has_gh = True
    except:
        has_gh = False
    
    if has_gh:
        print("\n☁️  Updating GitHub secret using gh CLI...")
        try:
            # Update the secret
            process = subprocess.run(
                ["gh", "secret", "set", "SESSION_DATA", "--repo", repo],
                input=session_b64,
                text=True,
                capture_output=True
            )
            if process.returncode == 0:
                print("✅ SESSION_DATA secret updated!")
                
                # Trigger workflow
                print("\n🚀 Triggering monitor workflow...")
                subprocess.run(
                    ["gh", "workflow", "run", "monitor.yml", "--repo", repo],
                    capture_output=True
                )
                print("✅ Workflow triggered!")
                
                print("\n" + "=" * 60)
                print("✅ SUCCESS! Monitoring will resume shortly.")
                print("=" * 60)
                print(f"\n📊 Check status: https://github.com/{repo}/actions")
            else:
                print(f"❌ Failed: {process.stderr}")
                print("\nMake sure you're logged in to GitHub CLI: gh auth login")
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        # No gh CLI - give manual instructions
        print("\n" + "=" * 60)
        print("📋 MANUAL UPDATE REQUIRED")
        print("=" * 60)
        print("\nGitHub CLI not found. Please update manually:")
        print(f"\n1. Go to: https://github.com/{repo}/settings/secrets/actions")
        print("2. Edit the 'SESSION_DATA' secret")
        print("3. Paste this value:\n")
        print("-" * 60)
        print(session_b64)
        print("-" * 60)
        print(f"\n4. Then trigger: https://github.com/{repo}/actions")


if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    main()
