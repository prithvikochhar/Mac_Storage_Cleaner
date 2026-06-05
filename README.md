# mac-storage-cleaner

A fast, safe macOS CLI tool to reclaim disk space by removing known junk files and identifying large stale items.

## Features

- **`clean`** — deletes browser caches (Chrome, Firefox, Safari), app caches in `~/Library/Caches`, conda package caches, log files in `~/Library/Logs`, and Trash; prompts for confirmation before deleting (bypass with `--yes`)
- **`--dry-run`** flag — shows exactly what *would* be deleted and how much space would be freed, without touching anything
- **`scan`** — finds files and folders larger than a configurable size that haven't been accessed in over 90 days (configurable), printing them as warnings

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

### Help

```bash
mac-storage-cleaner --help
mac-storage-cleaner clean --help
mac-storage-cleaner scan --help
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
| Trash | `~/.Trash` |

> **Note:** Always run `--dry-run` first to review what will be deleted. The `clean` command permanently removes files; there is no undo.

## Development

```bash
# Install dependencies
uv sync

# Run during development
uv run mac-storage-cleaner clean --dry-run
```
