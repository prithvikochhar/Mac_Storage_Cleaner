import os
import shutil
import stat
import subprocess
import time
from datetime import datetime
from pathlib import Path

import click


HOME = Path.home()


# ---------------------------------------------------------------------------
# Targets for the clean command
# ---------------------------------------------------------------------------

def _browser_cache_paths() -> list[Path]:
    return [
        HOME / "Library/Caches/Google/Chrome",
        HOME / "Library/Application Support/Google/Chrome/Default/Cache",
        HOME / "Library/Application Support/Google/Chrome/Default/Code Cache",
        HOME / "Library/Caches/Firefox",
        HOME / "Library/Safari/LocalStorage",
        HOME / "Library/Caches/com.apple.Safari",
    ]


def _app_cache_paths() -> list[Path]:
    cache_root = HOME / "Library/Caches"
    if not cache_root.exists():
        return []
    # Exclude system-critical caches; target per-app directories only
    excluded = {"com.apple.Safari"}
    return [
        p for p in cache_root.iterdir()
        if p.is_dir() and p.name not in excluded
    ]


def _conda_cache_paths() -> list[Path]:
    candidates = [
        HOME / "Library/Caches/conda",
        HOME / ".conda/pkgs",
    ]
    return [p for p in candidates if p.exists()]


def _log_paths() -> list[Path]:
    logs_root = HOME / "Library/Logs"
    if not logs_root.exists():
        return []
    return [p for p in logs_root.iterdir()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_dir(follow_symlinks=False):
                    total += _dir_size(Path(entry.path))
                else:
                    total += entry.stat(follow_symlinks=False).st_size
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        pass
    return total


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_dir():
        return _dir_size(path)
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _delete(path: Path, dry_run: bool) -> bool:
    """Delete a file or directory. Returns True if successful (or dry-run)."""
    if not path.exists():
        return False
    try:
        if dry_run:
            return True
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=False)
        else:
            path.unlink()
        return True
    except (PermissionError, OSError) as e:
        click.echo(click.style(f"  ! Could not delete {path}: {e}", fg="red"), err=True)
        if "Chrome" in str(path) and "Directory not empty" in str(e):
            click.echo(click.style("    → Close Chrome and try again.", fg="yellow"), err=True)
        return False


def _collect_clean_targets() -> list[tuple[str, list[Path]]]:
    return [
        ("Browser caches", _browser_cache_paths()),
        ("App caches (~/Library/Caches)", _app_cache_paths()),
        ("Conda cache", _conda_cache_paths()),
        ("Log files (~/Library/Logs)", _log_paths()),
    ]


def _available_dev_tools() -> list[str]:
    return [t for t in ("pip", "uv", "npm") if shutil.which(t) is not None]


def _dev_cache_dir(tool: str) -> "Path | None":
    try:
        if tool == "pip":
            r = subprocess.run(["pip", "cache", "dir"], capture_output=True, text=True, timeout=10)
        elif tool == "uv":
            r = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True, timeout=10)
        elif tool == "npm":
            r = subprocess.run(["npm", "config", "get", "cache"], capture_output=True, text=True, timeout=10)
        else:
            return None
        if r.returncode == 0:
            return Path(r.stdout.strip())
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _dev_cache_size(tool: str) -> int:
    cache_dir = _dev_cache_dir(tool)
    return _path_size(cache_dir) if cache_dir else 0


def _show_dev_cache_info(tool: str) -> None:
    try:
        if tool == "pip":
            r = subprocess.run(["pip", "cache", "info"], capture_output=True, text=True, timeout=15)
            for line in r.stdout.splitlines():
                click.echo(f"    {line}")
        elif tool == "uv":
            cache_dir = _dev_cache_dir("uv")
            if cache_dir:
                click.echo(f"    Cache directory: {cache_dir}")
                click.echo(f"    Cache size:       {_human_size(_path_size(cache_dir))}")
        elif tool == "npm":
            r = subprocess.run(["npm", "cache", "verify"], capture_output=True, text=True, timeout=30)
            output = r.stdout or r.stderr
            for line in output.splitlines():
                click.echo(f"    {line}")
    except (subprocess.TimeoutExpired, OSError) as e:
        click.echo(click.style(f"    ! Could not get {tool} cache info: {e}", fg="red"), err=True)


def _run_dev_cache_clean(tool: str) -> int:
    """Clean one dev tool's cache. Returns bytes freed (estimated as size before clean)."""
    size_before = _dev_cache_size(tool)
    click.echo(f"  {tool} cache: {_human_size(size_before)}")
    cmds = {
        "pip": ["pip", "cache", "purge"],
        "uv": ["uv", "cache", "clean"],
        "npm": ["npm", "cache", "clean", "--force"],
    }
    try:
        r = subprocess.run(cmds[tool], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            click.echo(f"  {click.style('✓', fg='green')} {tool} cache cleaned")
            return size_before
        click.echo(click.style(f"  ! {tool} cache clean failed: {r.stderr.strip()}", fg="red"), err=True)
    except (subprocess.TimeoutExpired, OSError) as e:
        click.echo(click.style(f"  ! Could not clean {tool} cache: {e}", fg="red"), err=True)
    return 0


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def _history_log_path() -> Path:
    return HOME / ".mac-storage-cleaner" / "history.log"


def _history_group_name(name: str) -> str:
    return name.split(" (")[0]


def _append_history(total_freed: int, group_totals: "list[tuple[str, int]]") -> None:
    log_path = _history_log_path()
    log_path.parent.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = ", ".join(
        f"{_history_group_name(name)}: {_human_size(size)}"
        for name, size in group_totals
        if size > 0
    )
    line = f"[{timestamp}] Cleaned {_human_size(total_freed)} — {parts}\n"
    with open(log_path, "a") as f:
        f.write(line)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def main():
    """Mac Storage Cleaner — reclaim disk space on macOS."""


@main.command()
@click.option("--dry-run", is_flag=True, default=False,
              help="Show what would be deleted without actually deleting anything.")
@click.option("--yes", "-y", is_flag=True, default=False,
              help="Skip the confirmation prompt.")
def clean(dry_run: bool, yes: bool):
    """Delete browser caches, app caches, logs, and developer caches."""
    if dry_run:
        click.echo(click.style("DRY RUN — nothing will be deleted.\n", fg="yellow", bold=True))

    groups = _collect_clean_targets()
    dev_tools = _available_dev_tools()

    if not dry_run:
        # Compute sizes and print a summary before asking for confirmation
        summary: list[tuple[str, int]] = []
        for group_name, paths in groups:
            group_size = sum(_path_size(p) for p in paths if p.exists())
            if group_size:
                summary.append((group_name, group_size))

        for tool in dev_tools:
            size = _dev_cache_size(tool)
            if size:
                summary.append((f"Developer caches ({tool})", size))

        if not summary:
            click.echo("Nothing to clean.")
            return

        click.echo(click.style("The following will be permanently deleted:", bold=True))
        total_preview = 0
        for group_name, size in summary:
            click.echo(f"  {group_name:<40} {_human_size(size):>10}")
            total_preview += size
        click.echo(f"\n  {'Total':<40} {_human_size(total_preview):>10}")

        if not yes:
            click.echo()
            confirmed = click.confirm(
                "Are you sure you want to permanently delete these files?",
                default=False,
            )
            if not confirmed:
                click.echo("Aborted.")
                return
        click.echo()

    total_freed = 0
    group_totals: list[tuple[str, int]] = []

    for group_name, paths in groups:
        click.echo(click.style(f"\n{group_name}", bold=True))
        group_freed = 0

        for path in paths:
            if not path.exists():
                continue
            size = _path_size(path)
            label = "  " + str(path).replace(str(HOME), "~")
            size_str = _human_size(size)

            if dry_run:
                click.echo(f"  [would delete] {label}  ({size_str})")
                group_freed += size
            else:
                if _delete(path, dry_run=False):
                    click.echo(f"  {click.style('✓', fg='green')} {label}  ({size_str})")
                    group_freed += size

        if group_freed:
            click.echo(f"  → {_human_size(group_freed)} {'would be freed' if dry_run else 'freed'}")

        group_totals.append((group_name, group_freed))
        total_freed += group_freed

    if dev_tools:
        click.echo(click.style("\nDeveloper caches", bold=True))
        dev_freed = 0
        for tool in dev_tools:
            if dry_run:
                size = _dev_cache_size(tool)
                click.echo(f"\n  {tool} cache ({_human_size(size)}):")
                _show_dev_cache_info(tool)
                dev_freed += size
            else:
                dev_freed += _run_dev_cache_clean(tool)
        if dev_freed:
            click.echo(f"  → {_human_size(dev_freed)} {'would be freed' if dry_run else 'freed'}")
        group_totals.append(("Developer caches", dev_freed))
        total_freed += dev_freed

    click.echo()
    verb = "would free" if dry_run else "freed"
    click.echo(click.style(f"Total {verb}: {_human_size(total_freed)}", bold=True))
    click.echo(click.style(
        "\nTip: To empty Trash, right-click the Trash icon in your Dock and select Empty Trash.",
        fg="cyan",
    ))

    if not dry_run and total_freed > 0:
        _append_history(total_freed, group_totals)


@main.command()
def history():
    """Show a table of past cleaning runs."""
    log_path = _history_log_path()
    if not log_path.exists():
        click.echo("No cleaning history found. Run `mac-storage-cleaner clean` to get started.")
        return

    lines = [l for l in log_path.read_text().splitlines() if l.strip()]
    if not lines:
        click.echo("No cleaning history found. Run `mac-storage-cleaner clean` to get started.")
        return

    click.echo(click.style(f"{'Date & Time':<22}  {'Total Cleaned':<15}  Details", bold=True))
    click.echo("-" * 100)
    for line in lines:
        if not line.startswith("["):
            continue
        try:
            bracket_end = line.index("]")
            timestamp = line[1:bracket_end]
            rest = line[bracket_end + 2:]
            parts = rest.split(" — ", 1)
            total = parts[0].replace("Cleaned ", "")
            details = parts[1] if len(parts) > 1 else ""
            click.echo(f"{timestamp:<22}  {total:<15}  {details}")
        except (ValueError, IndexError):
            click.echo(line)


@main.command()
@click.option("--min-size", default="1GB",
              help="Minimum file/folder size to report (e.g. 500MB, 1GB). Default: 1GB.")
@click.option("--days", default=90, show_default=True,
              help="Report items not accessed in this many days.")
@click.option("--path", "search_path", default=str(HOME), show_default=True,
              help="Directory to scan.")
def scan(min_size: str, days: int, search_path: str):
    """Find large files and folders that haven't been accessed recently."""
    min_bytes = _parse_size(min_size)
    if min_bytes is None:
        raise click.BadParameter(f"Cannot parse size: {min_size!r}. Use a number followed by B, KB, MB, or GB.")

    cutoff = time.time() - days * 86400
    root = Path(search_path).expanduser().resolve()

    click.echo(click.style(
        f"Scanning {root} for items >{min_size} not accessed in >{days} days...\n",
        bold=True,
    ))

    found = []
    _scan_recursive(root, min_bytes, cutoff, found, depth=0, max_depth=4)

    if not found:
        click.echo(click.style("No large stale items found.", fg="green"))
        return

    found.sort(key=lambda x: x[1], reverse=True)
    click.echo(click.style(
        f"{'Size':>10}  {'Last Accessed':<22}  Path", bold=True
    ))
    click.echo("-" * 80)
    for path, size, atime in found:
        age_days = int((time.time() - atime) / 86400)
        accessed_str = f"{age_days} days ago"
        label = str(path).replace(str(HOME), "~")
        click.echo(
            click.style(f"{_human_size(size):>10}", fg="yellow") +
            f"  {accessed_str:<22}  " +
            click.style(label, fg="red")
        )

    click.echo()
    click.echo(click.style(
        f"Warning: {len(found)} large stale item(s) found. "
        "Review before deleting — run `mac-storage-cleaner clean` to remove common junk.",
        fg="yellow", bold=True,
    ))


def _parse_size(s: str) -> int | None:
    s = s.strip().upper()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, multiplier in sorted(units.items(), key=lambda x: -len(x[0])):
        if s.endswith(suffix):
            try:
                return int(float(s[: -len(suffix)]) * multiplier)
            except ValueError:
                return None
    try:
        return int(s)
    except ValueError:
        return None


# Directories to skip during scan (system internals)
_SKIP_DIRS = {
    "Library/Application Support/MobileSync",  # iOS backups — can be huge but intentional
    ".Trash",
    "System",
    "private",
    "cores",
}

_SKIP_NAMES = {"node_modules", ".git", "__pycache__", ".venv", "venv"}


def _scan_recursive(
    path: Path,
    min_bytes: int,
    cutoff: float,
    results: list,
    depth: int,
    max_depth: int,
):
    if depth > max_depth:
        return
    try:
        entries = list(os.scandir(path))
    except (PermissionError, OSError):
        return

    for entry in entries:
        ep = Path(entry.path)

        if entry.name.startswith(".") and depth > 0:
            continue
        if entry.name in _SKIP_NAMES:
            continue

        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue

        if entry.is_symlink():
            continue

        if entry.is_dir(follow_symlinks=False):
            size = _dir_size(ep)
            atime = st.st_atime
            if size >= min_bytes and atime < cutoff:
                results.append((ep, size, atime))
            elif depth < max_depth:
                _scan_recursive(ep, min_bytes, cutoff, results, depth + 1, max_depth)
        else:
            size = st.st_size
            atime = st.st_atime
            if size >= min_bytes and atime < cutoff:
                results.append((ep, size, atime))


_APPS_MIN_BYTES = 500 * 1024 ** 2   # 500 MB
_APPS_DAYS = 180

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv", ".flv", ".webm"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".tiff", ".tif", ".heic", ".raw", ".bmp"}
_DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pages", ".numbers", ".key"}
_ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tar.bz2", ".tgz", ".rar", ".7z", ".tar.xz")


def _detect_type(path: Path) -> "tuple[str, str | None]":
    name = path.name.lower()
    if name.endswith(".app"):
        return "App", "(drag to Trash in Finder to uninstall properly)"
    if any(name.endswith(s) for s in _ARCHIVE_SUFFIXES):
        return "ZIP archive", "(likely already extracted — safe to delete)"
    if path.is_dir():
        try:
            path.relative_to(HOME / "Downloads")
            return "Folder", "(open in Finder to inspect before deleting)"
        except ValueError:
            return "Folder", None
    ext = path.suffix.lower()
    if ext in _VIDEO_EXTS:
        return "Video", None
    if ext in _IMAGE_EXTS:
        return "Image", None
    if ext in _DOC_EXTS:
        return "Document", None
    return "File", None


@main.command("find-large")
@click.option("--min-size", default="100MB", show_default=True,
              help="Minimum size for items in Downloads/Documents.")
@click.option("--days", default=30, show_default=True,
              help="Flag items in Downloads/Documents not accessed in this many days.")
def find_large(min_size: str, days: int):
    """Find large, unused files in Downloads, Documents, and Applications."""
    min_bytes = _parse_size(min_size)
    if min_bytes is None:
        raise click.BadParameter(
            f"Cannot parse size: {min_size!r}. Use a number followed by B, KB, MB, or GB."
        )

    now = time.time()
    cutoff_docs = now - days * 86400
    cutoff_apps = now - _APPS_DAYS * 86400

    results: list[tuple[Path, int, float]] = []

    for folder in [HOME / "Downloads", HOME / "Documents"]:
        if folder.exists():
            _scan_recursive(folder, min_bytes, cutoff_docs, results, depth=0, max_depth=2)

    apps_dir = Path("/Applications")
    if apps_dir.exists():
        try:
            for entry in os.scandir(apps_dir):
                if not entry.name.endswith(".app"):
                    continue
                ep = Path(entry.path)
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                size = _dir_size(ep)
                if size >= _APPS_MIN_BYTES and st.st_atime < cutoff_apps:
                    results.append((ep, size, st.st_atime))
        except (PermissionError, OSError):
            pass

    if not results:
        click.echo(click.style("No large unused items found.", fg="green"))
        return

    results.sort(key=lambda x: x[1], reverse=True)
    click.echo(click.style(f"{'Size':>10}  {'Last Accessed':<16}  {'Type':<14}  Path", bold=True))
    click.echo("-" * 90)
    for path, size, atime in results:
        age_days = int((now - atime) / 86400)
        label = str(path).replace(str(HOME), "~")
        type_label, note = _detect_type(path)
        click.echo(
            click.style(f"{_human_size(size):>10}", fg="yellow") +
            f"  {f'{age_days} days ago':<16}  " +
            click.style(f"{type_label:<14}", fg="cyan") +
            "  " +
            click.style(label, fg="red")
        )
        if note:
            click.echo(f"            {click.style(note, fg='yellow')}")

    click.echo()
    click.echo(click.style("How to clean these up:", bold=True))
    click.echo("  • Apps: drag them from /Applications to Trash, or use an uninstaller")
    click.echo("  • ZIP files and old downloads: review in Finder, then delete if no longer needed")
    click.echo("  • Large folders: open in Finder, inspect contents, then delete what you don't need")


@main.command("clean-docker")
@click.option("--dry-run", is_flag=True, default=False,
              help="Show Docker disk usage without removing anything.")
def clean_docker(dry_run: bool):
    """Remove unused Docker containers, images, volumes, and build cache."""
    if shutil.which("docker") is None:
        click.echo("Docker is not installed, skipping.")
        return

    try:
        probe = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        click.echo("Docker is not running. Start Docker Desktop and try again.")
        return

    if probe.returncode != 0:
        click.echo("Docker is not running. Start Docker Desktop and try again.")
        return

    if dry_run:
        click.echo(click.style("DRY RUN — Docker disk usage:\n", fg="yellow", bold=True))
        result = subprocess.run(["docker", "system", "df"], capture_output=True, text=True)
        click.echo(result.stdout)
        return

    click.echo(click.style("Pruning unused Docker data...\n", bold=True))
    result = subprocess.run(
        ["docker", "system", "prune", "-f"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(click.style(f"docker system prune failed:\n{result.stderr}", fg="red"), err=True)
        return

    lines = result.stdout.splitlines()
    for line in lines:
        if "Total reclaimed space" in line:
            click.echo(click.style(line, fg="green", bold=True))
        else:
            click.echo(line)
