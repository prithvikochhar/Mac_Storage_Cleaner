from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from mac_storage_cleaner.cli import (
    _app_cache_paths,
    _detect_type,
    _human_size,
    _is_excluded,
    _parse_size,
    _path_size,
    main,
)


# ---------------------------------------------------------------------------
# _parse_size
# ---------------------------------------------------------------------------

def test_parse_size_gb():
    assert _parse_size("1GB") == 1024 ** 3

def test_parse_size_mb():
    assert _parse_size("500MB") == 500 * 1024 ** 2

def test_parse_size_kb():
    assert _parse_size("100KB") == 100 * 1024

def test_parse_size_bare_int():
    assert _parse_size("1024") == 1024

def test_parse_size_invalid_returns_none():
    assert _parse_size("abc") is None


# ---------------------------------------------------------------------------
# _human_size
# ---------------------------------------------------------------------------

def test_human_size_bytes():
    assert _human_size(512) == "512.0 B"

def test_human_size_megabytes():
    assert _human_size(2 * 1024 ** 2) == "2.0 MB"

def test_human_size_gigabytes():
    assert _human_size(3 * 1024 ** 3) == "3.0 GB"


# ---------------------------------------------------------------------------
# _detect_type
# ---------------------------------------------------------------------------

def test_detect_type_app(tmp_path):
    p = tmp_path / "Xcode.app"
    p.mkdir()
    label, note = _detect_type(p)
    assert label == "App"
    assert note is not None

def test_detect_type_zip(tmp_path):
    p = tmp_path / "archive.zip"
    p.write_bytes(b"")
    label, note = _detect_type(p)
    assert label == "ZIP archive"
    assert note is not None

def test_detect_type_folder(tmp_path):
    p = tmp_path / "some_folder"
    p.mkdir()
    label, _ = _detect_type(p)
    assert label == "Folder"

def test_detect_type_video(tmp_path):
    p = tmp_path / "movie.mp4"
    p.write_bytes(b"")
    label, _ = _detect_type(p)
    assert label == "Video"

def test_detect_type_dmg(tmp_path):
    p = tmp_path / "SomeApp.dmg"
    p.write_bytes(b"")
    label, note = _detect_type(p)
    assert label == "Installer"
    assert note is not None

def test_detect_type_pkg(tmp_path):
    p = tmp_path / "Installer.pkg"
    p.write_bytes(b"")
    label, note = _detect_type(p)
    assert label == "Installer"
    assert note is not None


# ---------------------------------------------------------------------------
# _is_excluded
# ---------------------------------------------------------------------------

def test_is_excluded_exact_part():
    path = Path("/Users/user/Library/Caches/Spotify/Data")
    assert _is_excluded(path, {"spotify"})

def test_is_excluded_substring_in_parent():
    # --exclude Chrome must also match ~/Library/Caches/Google (contains "google"
    # which holds Chrome data), but more importantly it must match any path that
    # contains "chrome" anywhere, including ancestor directories.
    path = Path("/Users/user/Library/Caches/Google/Chrome")
    assert _is_excluded(path, {"chrome"})

def test_is_excluded_parent_directory():
    # The fix: "chrome" substring matches the parent Google/Chrome hierarchy
    path = Path("/Users/user/Library/Caches/Google")
    # "google" is not "chrome" — this should NOT be excluded by --exclude Chrome
    assert not _is_excluded(path, {"chrome"})

def test_is_excluded_no_match():
    path = Path("/Users/user/Library/Caches/Firefox")
    assert not _is_excluded(path, {"chrome", "spotify"})

def test_is_excluded_case_insensitive():
    path = Path("/Users/user/Library/Caches/CHROME/Cache")
    assert _is_excluded(path, {"chrome"})


# ---------------------------------------------------------------------------
# CLI — --help and error handling
# ---------------------------------------------------------------------------

def test_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output

def test_scan_invalid_size_exits_nonzero():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--min-size", "notasize"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# clean --dry-run on a tmp directory
# ---------------------------------------------------------------------------

def test_app_cache_no_double_count(tmp_path):
    """_app_cache_paths must not include a dir that is an ancestor of a browser path."""
    # Replicate the Google/Chrome overlap: Google is parent of Google/Chrome
    caches = tmp_path / "Library" / "Caches"
    chrome_dir = caches / "Google" / "Chrome"
    chrome_dir.mkdir(parents=True)
    (chrome_dir / "cache.bin").write_bytes(b"x" * 4096)

    other_dir = caches / "Spotify"
    other_dir.mkdir()
    (other_dir / "data.bin").write_bytes(b"x" * 2048)

    google_dir = caches / "Google"
    chrome_size = _path_size(chrome_dir)
    spotify_size = _path_size(other_dir)
    google_size = _path_size(google_dir)
    assert google_size == chrome_size  # Google only contains Chrome in this test

    with (
        patch("mac_storage_cleaner.cli.HOME", tmp_path),
        patch("mac_storage_cleaner.cli._browser_cache_paths", return_value=[chrome_dir]),
    ):
        app_paths = _app_cache_paths()

    # Google (ancestor of browser path) must be excluded; Spotify must remain
    assert google_dir not in app_paths
    assert other_dir in app_paths

    # Total across browser + app groups must not double-count Chrome's bytes
    total = _path_size(chrome_dir) + sum(_path_size(p) for p in app_paths)
    assert total == chrome_size + spotify_size


def test_clean_dry_run(tmp_path):
    cache_dir = tmp_path / "fake_cache"
    cache_dir.mkdir()
    (cache_dir / "junk.bin").write_bytes(b"x" * 1024)

    runner = CliRunner()
    with (
        patch("mac_storage_cleaner.cli._collect_clean_targets",
              return_value=[("Test caches", [cache_dir])]),
        patch("mac_storage_cleaner.cli._available_dev_tools", return_value=[]),
    ):
        result = runner.invoke(main, ["clean", "--dry-run"])

    assert result.exit_code == 0
    assert "DRY RUN" in result.output
