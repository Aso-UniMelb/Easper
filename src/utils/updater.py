"""
In-App Updater utility for Easper.
Handles checking for updates, downloading updated codebase, safely updating files,
and restarting the application.
"""
import os
import sys
import json
import shutil
import zipfile
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

from src import __version__
from src.utils.paths import get_base_path, get_temp_dir

GITHUB_OWNER = "Aso-UniMelb"
GITHUB_REPO = "Easper"
RAW_VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/version.json"
RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
ARCHIVE_ZIP_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/main.zip"


def get_local_version() -> str:
    """Get the current installed version string."""
    version_file = get_base_path() / "version.json"
    if version_file.is_file():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("version", __version__)
        except Exception:
            pass
    return __version__


def parse_version(ver_str: str) -> tuple:
    """Convert version string (e.g. 'v0.2.1' or '0.2.0') into tuple of ints for comparison."""
    cleaned = ver_str.strip().lstrip("v").split("-")[0]  # Remove 'v' and pre-release suffix
    parts = []
    for part in cleaned.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_version_newer(remote_version: str, local_version: str) -> bool:
    """Check if the remote version is strictly newer than the local version."""
    return parse_version(remote_version) > parse_version(local_version)


def check_for_updates(timeout: float = 4.0) -> dict:
    """
    Check GitHub for a newer version of Easper.
    
    Returns:
        dict with keys:
            'has_update' (bool),
            'current_version' (str),
            'latest_version' (str),
            'changelog' (str),
            'release_date' (str),
            'download_url' (str),
            'error' (str or None)
    """
    current_version = get_local_version()
    result = {
        "has_update": False,
        "current_version": current_version,
        "latest_version": current_version,
        "changelog": "",
        "release_date": "",
        "download_url": ARCHIVE_ZIP_URL,
        "error": None
    }

    req = urllib.request.Request(
        RAW_VERSION_URL,
        headers={"User-Agent": f"Easper-Updater/{current_version}"}
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                remote_version = data.get("version", current_version)
                result["latest_version"] = remote_version
                result["changelog"] = data.get("changelog", "Bug fixes and improvements.")
                result["release_date"] = data.get("release_date", "")
                result["download_url"] = data.get("download_url", ARCHIVE_ZIP_URL)
                result["has_update"] = is_version_newer(remote_version, current_version)
                return result
    except urllib.error.URLError as e:
        result["error"] = f"Network error: {e.reason if hasattr(e, 'reason') else e}"
    except Exception as e:
        result["error"] = str(e)

    # Fallback to GitHub Releases API if raw version.json was unavailable
    try:
        rel_req = urllib.request.Request(
            RELEASE_API_URL,
            headers={"User-Agent": f"Easper-Updater/{current_version}"}
        )
        with urllib.request.urlopen(rel_req, timeout=timeout) as response:
            if response.status == 200:
                rel_data = json.loads(response.read().decode("utf-8"))
                tag_name = rel_data.get("tag_name", "").lstrip("v")
                if tag_name:
                    result["latest_version"] = tag_name
                    result["changelog"] = rel_data.get("body", "Bug fixes and improvements.")
                    result["release_date"] = rel_data.get("published_at", "")[:10]
                    result["download_url"] = rel_data.get("zipball_url", ARCHIVE_ZIP_URL)
                    result["has_update"] = is_version_newer(tag_name, current_version)
                    result["error"] = None
    except Exception:
        pass

    return result


def download_and_apply_update(download_url: str = None, progress_callback=None) -> bool:
    """
    Download updated codebase from GitHub and safely overwrite src/ and root files.
    Preserves user_models/, word_lists/, and venv/.
    
    Args:
        download_url: Custom download URL or default GitHub main branch zip.
        progress_callback: Callback fn(percent_float, status_str)
        
    Returns:
        bool: True on success, raises Exception on failure.
    """
    if not download_url:
        download_url = ARCHIVE_ZIP_URL

    base_path = get_base_path()
    src_path = base_path / "src"
    temp_update_dir = get_temp_dir() / "update_cache"
    zip_target_path = temp_update_dir / "easper_update.zip"
    extract_target_dir = temp_update_dir / "extracted"
    backup_src_dir = base_path / "src_backup"

    # Ensure clean temp directories
    shutil.rmtree(temp_update_dir, ignore_errors=True)
    temp_update_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(0.1, "Connecting to GitHub...")

    # 1. Download zip archive
    req = urllib.request.Request(
        download_url,
        headers={"User-Agent": f"Easper-Updater/{get_local_version()}"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30.0) as response:
            total_size = response.headers.get('content-length')
            total_bytes = int(total_size) if total_size else 0
            downloaded = 0
            block_size = 65536

            with open(zip_target_path, "wb") as f:
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    downloaded += len(buffer)
                    f.write(buffer)
                    if total_bytes > 0 and progress_callback:
                        pct = 0.1 + 0.5 * (downloaded / total_bytes)
                        progress_callback(pct, f"Downloading: {downloaded // 1024} KB / {total_bytes // 1024} KB")
                    elif progress_callback:
                        progress_callback(0.35, f"Downloading: {downloaded // 1024} KB...")
    except Exception as e:
        raise RuntimeError(f"Failed to download update package: {e}")

    if progress_callback:
        progress_callback(0.65, "Extracting and verifying package...")

    # 2. Extract ZIP archive
    try:
        with zipfile.ZipFile(zip_target_path, "r") as zip_ref:
            zip_ref.extractall(extract_target_dir)
    except Exception as e:
        raise RuntimeError(f"Corrupted update archive: {e}")

    # Find the extracted root (GitHub wraps in Easper-main/ or Easper-tag/)
    extracted_root = extract_target_dir
    extracted_subdirs = [d for d in extract_target_dir.iterdir() if d.is_dir()]
    if len(extracted_subdirs) == 1 and not (extract_target_dir / "src").exists():
        extracted_root = extracted_subdirs[0]

    extracted_src = extracted_root / "src"
    if not extracted_src.exists():
        raise RuntimeError("Invalid update archive: 'src' folder not found in package.")

    if progress_callback:
        progress_callback(0.75, "Creating safety backup of current code...")

    # 3. Create backup of current src/
    if backup_src_dir.exists():
        shutil.rmtree(backup_src_dir, ignore_errors=True)
    if src_path.exists():
        shutil.copytree(src_path, backup_src_dir)

    if progress_callback:
        progress_callback(0.85, "Installing updated files...")

    # 4. Overwrite src/ and root update files
    try:
        # Copy files from extracted_src to src_path
        for root, dirs, files in os.walk(extracted_src):
            rel_dir = os.path.relpath(root, extracted_src)
            dest_dir = src_path if rel_dir == "." else src_path / rel_dir
            dest_dir.mkdir(parents=True, exist_ok=True)

            for file in files:
                src_file = Path(root) / file
                dest_file = dest_dir / file
                shutil.copy2(src_file, dest_file)

        # Copy top-level metadata files if present in update
        for meta_file in ["version.json", "requirements.txt", "download-whisper-small.py", "README.md"]:
            src_meta = extracted_root / meta_file
            if src_meta.is_file():
                shutil.copy2(src_meta, base_path / meta_file)

        # 5. Check requirements.txt update
        req_file = base_path / "requirements.txt"
        if req_file.exists():
            if progress_callback:
                progress_callback(0.92, "Checking dependencies...")

    except Exception as e:
        # Rollback on error
        if backup_src_dir.exists() and src_path.exists():
            shutil.rmtree(src_path, ignore_errors=True)
            shutil.copytree(backup_src_dir, src_path)
        raise RuntimeError(f"Update failed during file replacement. Rolled back successfully. Error: {e}")

    # 6. Cleanup
    shutil.rmtree(backup_src_dir, ignore_errors=True)
    shutil.rmtree(temp_update_dir, ignore_errors=True)

    if progress_callback:
        progress_callback(1.0, "Update completed successfully!")

    return True


def restart_application():
    """Restart the Easper application."""
    base_path = get_base_path()
    main_py = str(base_path / "src" / "main.py")
    python_exe = sys.executable

    # Spawn new process
    if sys.platform == "win32":
        subprocess.Popen([python_exe, main_py], cwd=str(base_path), creationflags=subprocess.CREATE_NEW_CONSOLE if not getattr(sys, 'frozen', False) else 0)
    else:
        subprocess.Popen([python_exe, main_py], cwd=str(base_path))

    # Exit current process
    os._exit(0)
