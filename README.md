# mac-storage-cleaner

A fast, safe macOS CLI tool to reclaim disk space by removing known junk files and identifying large stale items.

## Features

- **`clean`** — deletes browser caches (Chrome, Firefox, Safari), app caches in `~/Library/Caches`, conda package caches, log files in `~/Library/Logs`, and developer caches (pip, uv, npm); prompts for confirmation before deleting (bypass with `--yes`)
- **`--dry-run`** flag — shows exactly what *would* be deleted and how much space would be freed, without touching anything
- **`scan`** — finds files and folders larger than a configurable size that haven't been accessed in over 90 days (configurable), printing them as warnings
- **`find-large`** — scans `~/Downloads`, `~/Documents`, and `/Applications` for large, unused items; shows type (App, ZIP archive, Folder, Video, Image, Document, or File) with context-specific cleanup tips
- **`clean-docker`** — removes unused Docker containers, images, volumes, and build cache via `docker system prune`
- **`history`** — displays a table of past cleaning runs with totals and per-category breakdown
- **`schedule`** / **`unschedule`** — installs or removes a monthly launchd job that runs a dry-run scan on the 1st of each month at 9am and sends a macOS notification

## Requirements

- macOS
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)

## Installation

```bash
# Install from GitHub
uv tool install "git+https://github.com/prithvikochhar/Mac_Storage_Cleaner"
```

Or install from a local clone:

```bash
uv tool install .
```

Or run without installing:

```bash
uv run mac-storage-cleaner <command>
```

## Usage

### Preview what would be cleaned (safe — no deletions)

```bash
mac-storage-cleaner clean --dry-run
```

### Actually clean junk files

```bash
mac-storage-cleaner clean
# You will be prompted to confirm before any files are deleted.
# To skip the prompt (e.g. in scripts):
mac-storage-cleaner clean --yes
```

After cleaning, a disk space summary is always printed (both dry-run and real runs):

```
Free space: 45.2 GB → 52.7 GB (freed 7.5 GB)
```

For dry-run, the estimated free space after is shown instead.

### Clean only specific categories

```bash
# Clean only browser/app caches and log files
mac-storage-cleaner clean --categories caches,logs

# Clean only developer tool caches
mac-storage-cleaner clean --categories developer

# Clean everything including Docker (adds docker system prune)
mac-storage-cleaner clean --categories caches,logs,conda,developer,docker
```

Available categories: `caches`, `logs`, `conda`, `developer`, `docker`.  
If `--categories` is not specified, all categories except `docker` are cleaned (default behaviour unchanged).  
A note is printed at the top showing which categories are active.

### Find large stale files (default: >1 GB, not accessed in 90+ days)

```bash
mac-storage-cleaner scan
```

### Scan with custom thresholds

```bash
# Find items larger than 500 MB not accessed in 60+ days
mac-storage-cleaner scan --min-size 500MB --days 60

# Scan a specific directory
mac-storage-cleaner scan --path ~/Downloads --min-size 100MB
```

### Find large unused items in Downloads, Documents, and Applications

```bash
mac-storage-cleaner find-large
```

This scans:
- `~/Downloads` and `~/Documents` — items >100 MB not accessed in 30+ days
- `/Applications` — apps >500 MB not opened in 180+ days

Each result shows its **type** (App, ZIP archive, Folder, Video, Image, Document, or File) with a context-specific note:
- ZIP archives are flagged as likely safe to delete
- Apps remind you to drag to Trash in Finder (not just delete)
- Old folders in Downloads prompt you to inspect before deleting

Output ends with a **How to clean these up:** guide.

```bash
# Customize thresholds for Downloads/Documents
mac-storage-cleaner find-large --min-size 200MB --days 60

# Interactively delete items one by one
mac-storage-cleaner find-large --interactive
# or: mac-storage-cleaner find-large -i
```

After showing the results table, `--interactive` prompts for each non-app item:

```
Delete ~/Downloads/old-backup.zip? [y/n/q(uit)]: 
```

- `y` deletes the item and prints how much was freed
- `n` skips to the next item
- `q` exits the interactive session without deleting remaining items
- Items inside `/Applications` are always skipped with a reminder to use Finder
- A summary is printed at the end: `Deleted X items, freed Y GB`

### View cleaning history

```bash
mac-storage-cleaner history
```

Displays a table of every past `clean` run with timestamp, total freed, and per-category breakdown. The log is stored at `~/.mac-storage-cleaner/history.log`.

### Schedule monthly scans

```bash
# Install a launchd job: runs a dry-run scan on the 1st of each month at 9am
# and sends a macOS notification when complete
mac-storage-cleaner schedule

# Check whether the scheduler is installed
mac-storage-cleaner schedule --status

# Remove the scheduler
mac-storage-cleaner unschedule
```

The notification reads: *"Monthly scan complete. Run mac-storage-cleaner history to see results."*

### Clean up unused Docker data

```bash
# See what would be freed (no deletions)
mac-storage-cleaner clean-docker --dry-run

# Actually prune unused Docker data
mac-storage-cleaner clean-docker
```

Requires Docker to be installed and Docker Desktop to be running. If Docker is not installed the command prints a notice and exits cleanly.

### Help

```bash
mac-storage-cleaner --help
mac-storage-cleaner clean --help
mac-storage-cleaner scan --help
mac-storage-cleaner find-large --help
mac-storage-cleaner clean-docker --help
mac-storage-cleaner history --help
mac-storage-cleaner schedule --help
```

## What gets cleaned

| Category | Paths |
|---|---|
| Chrome cache | `~/Library/Caches/Google/Chrome`, `~/Library/Application Support/Google/Chrome/Default/Cache` |
| Firefox cache | `~/Library/Caches/Firefox` |
| Safari cache | `~/Library/Caches/com.apple.Safari`, `~/Library/Safari/LocalStorage` |
| App caches | All subdirectories of `~/Library/Caches` |
| Conda cache | `~/Library/Caches/conda`, `~/.conda/pkgs` (only if present) |
| Log files | All items in `~/Library/Logs` |
| Developer caches | pip, uv, and npm caches (only for tools that are installed) |

> **Tip:** Always run `--dry-run` first to preview what will be deleted.

## Development

```bash
# Install dependencies
uv sync

# Run during development
uv run mac-storage-cleaner clean --dry-run
```
