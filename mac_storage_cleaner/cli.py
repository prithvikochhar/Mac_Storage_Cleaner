import os
import shutil
import stat
import time
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


def _trash_path() -> Path:
    return HOME / ".Trash"


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
        return False


def _collect_clean_targets() -> list[tuple[str, list[Path]]]:
    return [
        ("Browser caches", _browser_cache_paths()),
        ("App caches (~/Library/Caches)", _app_cache_paths()),
        ("Conda cache", _conda_cache_paths()),
        ("Log files (~/Library/Logs)", _log_paths()),
        ("Trash (~/.Trash)", [_trash_path()]),
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def main():
    """Mac Storage Cleaner — reclaim disk space on macOS."""


@main.command()
@click.option("--dry-run", is_flag=True, default=False,
              help="Show what would be deleted without actually deleting anything.")
def clean(dry_run: bool):
    """Delete browser caches, app caches, logs, and Trash."""
    if dry_run:
        click.echo(click.style("DRY RUN — nothing will be deleted.\n", fg="yellow", bold=True))

    total_freed = 0
    groups = _collect_clean_targets()

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

        total_freed += group_freed

    click.echo()
    verb = "would free" if dry_run else "freed"
    click.echo(click.style(f"Total {verb}: {_human_size(total_freed)}", bold=True))


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
