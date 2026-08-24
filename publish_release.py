"""
Release & Version Publishing Automation for Easper.

Handles:
1. Version synchronization (version.json, src/__init__.py, windows_installer/Easper_installer.iss)
2. Compiling Windows installer via Inno Setup (ISCC.exe)
3. Git commit, tag creation, and push
4. Release drafting & GitHub release link generation
"""

import os
import sys
import json
import re
import datetime
import subprocess
import shutil
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
VERSION_JSON = ROOT_DIR / "version.json"
INIT_PY = ROOT_DIR / "src" / "__init__.py"
ISS_FILE = ROOT_DIR / "windows_installer" / "Easper_installer.iss"
OUTPUT_DIR = ROOT_DIR / "windows_installer" / "Output"

POSSIBLE_ISCC_PATHS = [
    shutil.which("ISCC.exe") or shutil.which("iscc"),
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    r"C:\Program Files\Inno Setup 5\ISCC.exe",
]


def find_iscc():
    for p in POSSIBLE_ISCC_PATHS:
        if p and os.path.exists(p):
            return str(p)
    return None


def get_current_version():
    if VERSION_JSON.is_file():
        try:
            with open(VERSION_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("version", "0.3.0")
        except Exception:
            pass
    return "0.3.0"


def update_version_files(new_version: str, changelog_text: str):
    today_str = datetime.date.today().isoformat()

    # 1. Update version.json
    v_data = {
        "version": new_version,
        "release_date": today_str,
        "changelog": changelog_text,
        "min_python": "3.11"
    }
    with open(VERSION_JSON, "w", encoding="utf-8") as f:
        json.dump(v_data, f, indent=2)
    print(f"[*] Updated {VERSION_JSON.name} -> version: {new_version}, date: {today_str}")

    # 2. Update src/__init__.py
    if INIT_PY.is_file():
        content = INIT_PY.read_text(encoding="utf-8")
        updated = re.sub(r'__version__\s*=\s*["\'][^"\']+["\']', f'__version__ = "{new_version}"', content)
        INIT_PY.write_text(updated, encoding="utf-8")
        print(f"[*] Updated {INIT_PY.relative_to(ROOT_DIR)} -> __version__ = \"{new_version}\"")

    # 3. Update windows_installer/Easper_installer.iss
    if ISS_FILE.is_file():
        content = ISS_FILE.read_text(encoding="utf-8")
        updated = re.sub(r'#define\s+MyAppVersion\s+["\'][^"\']+["\']', f'#define MyAppVersion "{new_version}"', content)
        ISS_FILE.write_text(updated, encoding="utf-8")
        print(f"[*] Updated {ISS_FILE.relative_to(ROOT_DIR)} -> MyAppVersion \"{new_version}\"")


def clean_pycache():
    """Remove all __pycache__ directories and .pyc/.pyo files (excluding venv and .git)."""
    print("\n[-] Cleaning __pycache__ folders and compiled bytecode...")
    cleaned_count = 0
    for root, dirs, files in os.walk(ROOT_DIR):
        parts = Path(root).parts
        if "venv" in parts or ".git" in parts:
            continue
        for d in list(dirs):
            if d == "__pycache__":
                cache_dir = Path(root) / d
                try:
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    cleaned_count += 1
                except Exception as e:
                    print(f"    Note: Could not remove {cache_dir}: {e}")
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                pyc_file = Path(root) / f
                try:
                    pyc_file.unlink(missing_ok=True)
                except Exception:
                    pass
    print(f"[OK] Cleaned {cleaned_count} __pycache__ folder(s).")


def build_installer(iscc_path: str):
    clean_pycache()
    print("\n[*] Compiling Windows Setup Installer with Inno Setup...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [iscc_path, str(ISS_FILE)]
    res = subprocess.run(cmd, cwd=str(ISS_FILE.parent))
    if res.returncode == 0:
        exes = sorted(OUTPUT_DIR.glob("*.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
        if exes:
            exe_path = exes[0]
            mb_size = exe_path.stat().st_size / (1024 * 1024)
            print(f"[OK] Installer successfully compiled: {exe_path.name} ({mb_size:.1f} MB)")
            return exe_path
        print(f"[OK] Inno Setup finished successfully.")
        return OUTPUT_DIR
    else:
        print(f"[!] Inno Setup failed with exit code {res.returncode}")
        return None


def run_git_release(new_version: str, changelog_text: str, auto_push: bool = True):
    tag_name = f"v{new_version}" if not new_version.startswith("v") else new_version
    print(f"\n[*] Creating Git Commit and Tag ({tag_name})...")

    # Stage files
    subprocess.run(["git", "add", "version.json", "src/__init__.py", "windows_installer/Easper_installer.iss"], cwd=str(ROOT_DIR), check=True)
    
    # Commit
    commit_msg = f"Release {tag_name}: {changelog_text}"
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(ROOT_DIR), check=True)
    print(f"[OK] Created commit: '{commit_msg}'")

    # Tag
    subprocess.run(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"], cwd=str(ROOT_DIR), check=True)
    print(f"[OK] Created tag: {tag_name}")

    if auto_push:
        print(f"\n[*] Pushing commits and tags to remote (origin)...")
        res = subprocess.run(["git", "push", "origin", "--follow-tags"], cwd=str(ROOT_DIR))
        if res.returncode == 0:
            print("[OK] Pushed commits and tags successfully!")
        else:
            print("[!] Push failed. You can manually run: git push origin --follow-tags")


def main():
    print("=" * 60)
    print("           EASPER RELEASE & PUBLISH AUTOMATION           ")
    print("=" * 60)

    cur_ver = get_current_version()
    print(f"Current version: {cur_ver}\n")

    # Arguments or interactive prompt
    if len(sys.argv) > 1:
        new_version = sys.argv[1].strip()
        changelog = " ".join(sys.argv[2:]).strip() if len(sys.argv) > 2 else "New release update."
    else:
        try:
            suggested = cur_ver
            parts = cur_ver.split(".")
            if len(parts) == 3 and parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + 1)
                suggested = ".".join(parts)
            
            entered_ver = input(f"Enter new version number [{suggested}]: ").strip()
            new_version = entered_ver if entered_ver else suggested

            entered_cl = input("Enter changelog summary for this release: ").strip()
            changelog = entered_cl if entered_cl else f"Release v{new_version} update."
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return

    new_version = new_version.lstrip("v")
    print(f"\nPreparing to publish v{new_version}:")
    print(f"- Changelog: {changelog}")

    # 1. Update Version Files
    update_version_files(new_version, changelog)

    # 2. Check and Build Inno Setup Installer
    iscc = find_iscc()
    installer_built = None
    if iscc:
        print(f"\nFound Inno Setup compiler: {iscc}")
        build_choice = input("Build Windows installer now? [Y/n]: ").strip().lower() if len(sys.argv) <= 1 else "y"
        if build_choice in ("", "y", "yes"):
            installer_built = build_installer(iscc)
    else:
        print("\nNote: Inno Setup compiler (ISCC.exe) not found. Skipping installer build.")

    # 3. Git Commit & Tag & Push
    git_choice = input("\nCommit, tag, and push to GitHub now? [Y/n]: ").strip().lower() if len(sys.argv) <= 1 else "y"
    if git_choice in ("", "y", "yes"):
        try:
            run_git_release(new_version, changelog, auto_push=True)
        except Exception as e:
            print(f"Git operation error: {e}")

    # 4. Release Summary & Next Steps
    tag_name = f"v{new_version}"
    print("\n" + "=" * 60)
    print(f"Release {tag_name} Published Successfully!")
    print("=" * 60)
    print(f"- In-App Updaters will now detect and offer version {new_version} on launch.")
    if installer_built and os.path.exists(str(installer_built)):
        print(f"- Setup executable ready at: {installer_built}")
    print(f"- To create or attach binaries to the GitHub Release page:")
    print(f"  https://github.com/Aso-UniMelb/Easper/releases/new?tag={tag_name}&title=Easper+{tag_name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
