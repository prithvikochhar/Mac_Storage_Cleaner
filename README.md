# mac-storage-cleaner

A fast, safe macOS CLI tool to reclaim disk space by removing known junk files and identifying large stale items.

## Features

- **`clean`** — deletes browser caches (Chrome, Firefox, Safari), app caches in `~/Library/Caches`, conda package caches, and log files in `~/Library/Logs`; prompts for confirmation before deleting (bypass with `--yes`)
- **`--dry-run`** flag — shows exactly what *would* be deleted and how much space would be freed, without touching anything
- **`scan`** — finds files and folders larger than a configurable size that haven't been accessed in over 90 days (configurable), printing them as warnings
- **`find-large`** — scans `~/Downloads`, `~/Documents`, and `/Applications` for large, unused items and prints a sorted table with size, last-accessed date, and path
- **`clean-docker`** — removes unused Docker containers, images, volumes, and build cache via `docker system prune`

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

```bash
# Customize thresholds for Downloads/Documents
mac-storage-cleaner find-large --min-size 200MB --days 60
```

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

> **Tip:** Always run `--dry-run` first to preview what will be deleted.

## Development

```bash
# Install dependencies
uv sync

# Run during development
uv run mac-storage-cleaner clean --dry-run
```
