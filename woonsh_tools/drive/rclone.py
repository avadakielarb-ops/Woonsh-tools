"""
rclone integration — download, install, Drive upload with SHA-256 verification.
From X-File rclone_download.py + x-file.pyw drive sections.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

PRIMARY = "https://downloads.rclone.org/rclone-current-windows-amd64.zip"
REMOTE = "woonsh"


def fetch(url, progress=None):
    """Download a URL with progress callback(done, total)."""
    req = Request(url, headers={"User-Agent": "WoonshTools/1.0", "Accept": "*/*"})
    with urlopen(req, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        buffer = io.BytesIO()
        while True:
            chunk = response.read(262144)
            if not chunk:
                break
            if buffer.tell() + len(chunk) > 100 * 1024 * 1024:
                raise ValueError("Слишком большой архив rclone.")
            buffer.write(chunk)
            if progress:
                progress(buffer.tell(), total)
        return buffer.getvalue()


def github_asset():
    """Get the latest rclone Windows x64 asset from GitHub Releases."""
    req = Request(
        "https://api.github.com/repos/rclone/rclone/releases/latest",
        headers={"User-Agent": "WoonshTools/1.0",
                 "Accept": "application/vnd.github+json"})
    with urlopen(req, timeout=20) as response:
        release = json.loads(response.read(2_000_000))
    asset = next(
        (a for a in release.get("assets", [])
         if a["name"].endswith("-windows-amd64.zip")), None)
    if not asset:
        raise ValueError(
            "В официальном релизе rclone не найден архив Windows x64.")
    url = asset.get("browser_download_url", "")
    digest = asset.get("digest", "")
    if (not url.startswith(
            "https://github.com/rclone/rclone/releases/download/")
            or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)):
        raise ValueError("Не удалось проверить источник архива rclone.")
    return url, digest.split(":")[1].lower()


def install_from_archive(archive, folder):
    """Extract rclone.exe from a ZIP archive into folder."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        names = [n for n in zf.namelist()
                 if n.lower().endswith("/rclone.exe")
                 or n.lower() == "rclone.exe"]
        if len(names) != 1:
            raise ValueError("В архиве не найден единственный rclone.exe.")
        if zf.getinfo(names[0]).file_size > 150 * 1024 * 1024:
            raise ValueError("Слишком большой rclone.exe.")
        fd, path = tempfile.mkstemp(
            prefix="rclone-", suffix=".download", dir=str(folder))
        try:
            with os.fdopen(fd, "wb") as stream, zf.open(names[0]) as source:
                import shutil
                shutil.copyfileobj(source, stream)
            with open(path, "rb") as stream:
                if stream.read(2) != b"MZ":
                    raise ValueError("Файл не является Windows EXE.")
            target = folder / "rclone.exe"
            os.replace(path, target)
            return str(target)
        finally:
            if os.path.exists(path):
                os.unlink(path)


def download_rclone(folder, progress=None, status=None):
    """Download rclone from official sources with fallback."""
    notify = status or (lambda message: None)
    try:
        notify("Скачиваю rclone с downloads.rclone.org…")
        return install_from_archive(fetch(PRIMARY, progress), folder)
    except Exception:
        notify("Основной источник недоступен. Скачиваю из GitHub…")
    try:
        url, digest = github_asset()
        archive = fetch(url, progress)
        if hashlib.sha256(archive).hexdigest() != digest:
            raise ValueError("Контрольная сумма rclone не совпала.")
        return install_from_archive(archive, folder)
    except Exception as exc:
        raise RuntimeError(
            "Не удалось скачать rclone. Причина: "
            + type(exc).__name__) from exc


def find_rclone(saved=""):
    """Find rclone executable, checking saved path and common locations."""
    for candidate in [saved, "rclone", "rclone.exe"]:
        if candidate and os.path.isfile(candidate):
            return candidate
    return ""


def drive_folder_id(url_or_id):
    """Extract Google Drive folder ID from URL or raw ID."""
    if not url_or_id:
        return ""
    match = re.search(r"/folders/([A-Za-z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", url_or_id.strip()):
        return url_or_id.strip()
    return ""


def remote_of(folder_id):
    """Build rclone remote path for a Drive folder."""
    if folder_id:
        return f"{REMOTE},root_folder_id={folder_id}:"
    return f"{REMOTE}:"


def run_rclone(exe, args, timeout=300):
    """Run an rclone command and return (code, stdout, stderr)."""
    result = subprocess.run(
        [exe] + args,
        capture_output=True, text=True, timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    return result.returncode, result.stdout, result.stderr


def check_drive(exe, folder_id):
    """Verify Drive access. Returns (ok, message)."""
    target = remote_of(folder_id)
    code, out, err = run_rclone(
        exe, ["lsf", target, "--max-depth", "0"], timeout=30)
    if code == 0:
        return True, "Google Drive доступен."
    return False, "Нет доступа к Google Drive: " + (err or "").strip()[:200]


def upload_file(exe, src, dest_name, folder_id):
    """Upload a single file to Drive via rclone. Returns (ok, error)."""
    code, out, err = run_rclone(
        exe,
        ["copyto", src, remote_of(folder_id) + dest_name,
         "--retries", "3", "--low-level-retries", "10",
         "--drive-chunk-size", "64M"],
        timeout=600)
    if code == 0:
        return True, ""
    return False, (err or "").strip()[:300]


def list_drive_files(exe, folder_id):
    """List files in a Drive folder as JSON. Returns list of dicts."""
    code, out, err = run_rclone(
        exe,
        ["lsjson", remote_of(folder_id), "--files-only", "--no-modtime"],
        timeout=120)
    if code != 0:
        return []
    return json.loads(out.strip() or "[]")


def file_sha256(path):
    """Compute SHA-256 of a local file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
