"""
setup.py — One-click setup script for the Auto Job Apply System.
Installs all dependencies, sets up Playwright, and validates the environment.
"""

import subprocess
import sys
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent

def run(cmd, **kwargs):
    print(f"\n$ {cmd}")
    result = subprocess.run(cmd, shell=True, **kwargs)
    return result.returncode == 0

def main():
    print("=" * 60)
    print("  Auto Job Apply System — Setup")
    print("=" * 60)

    # 1. Copy .env.template → .env
    env_file = BASE_DIR / ".env"
    env_template = BASE_DIR / ".env.template"
    if not env_file.exists():
        shutil.copy(env_template, env_file)
        print(f"\n✓ Created .env from template")
        print(f"  → EDIT {env_file} with your credentials before running!")
    else:
        print(f"\n✓ .env already exists")

    # 2. Install Python packages
    print("\n[1/4] Installing Python packages...")
    ok = run(f"{sys.executable} -m pip install -r requirements.txt --quiet")
    if ok:
        print("✓ Python packages installed")
    else:
        print("✗ Failed to install packages — check requirements.txt")
        sys.exit(1)

    # 3. Install Playwright browsers
    print("\n[2/4] Installing Playwright Chromium browser...")
    ok = run(f"{sys.executable} -m playwright install chromium")
    if ok:
        print("✓ Playwright Chromium installed")
    else:
        print("✗ Playwright install failed")
        print("  Try manually: playwright install chromium")

    # 4. Create directories
    print("\n[3/4] Creating directories...")
    for d in ["logs", "db"]:
        (BASE_DIR / d).mkdir(exist_ok=True)
    print("✓ Directories ready")

    # 5. Validate setup
    print("\n[4/4] Validating installation...")
    ok = run(f"{sys.executable} main.py --test")

    print("\n" + "=" * 60)
    if ok:
        print("✅ Setup complete!")
    else:
        print("⚠️  Setup complete with warnings (check output above)")

    print("""
Next steps:
  1. Edit .env with your credentials:
       - LinkedIn/Naukri/Indeed passwords
       - Gmail App Password (for email monitoring)
       - CapSolver API key (optional, for CAPTCHA)

  2. Run a dry run to test scraping:
       python main.py --dry-run

  3. Start the full system:
       python main.py

  4. Open the dashboard:
       http://localhost:5000
""")

if __name__ == "__main__":
    main()
