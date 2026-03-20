"""
Tests for jules-cli-scan feature.
"""
import os
import tempfile
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from argos import FileScanner


# ---------------------------------------------------------------------------
# Property 2: File discovery respects ignore list
# Feature: jules-cli-scan, Property 2: File discovery respects ignore list
# Validates: Requirements 2.1, 2.2
# ---------------------------------------------------------------------------

IGNORED_DIR_NAMES = list(FileScanner.IGNORED_DIRS)
IGNORED_FILE_NAMES = list(FileScanner.IGNORED_FILES)


@given(
    ignored_dirs=st.lists(
        st.sampled_from(IGNORED_DIR_NAMES), min_size=1, max_size=4, unique=True
    ),
    ignored_files=st.lists(
        st.sampled_from(IGNORED_FILE_NAMES), min_size=0, max_size=1, unique=True
    ),
)
@settings(max_examples=100)
def test_ignored_dirs_and_files_not_discovered(ignored_dirs, ignored_files):
    """
    **Validates: Requirements 2.1, 2.2**

    For any directory tree containing subdirectories or files with names in the
    ignore list, none of those paths should appear in the list returned by
    FileScanner.discover_files.
    """
    scanner = FileScanner()

    with tempfile.TemporaryDirectory() as root:
        # Create ignored subdirectories with a UTF-8 text file inside each
        for d in ignored_dirs:
            ignored_dir_path = os.path.join(root, d)
            os.makedirs(ignored_dir_path, exist_ok=True)
            # Place a valid text file inside so it would be discovered if not filtered
            with open(os.path.join(ignored_dir_path, "secret.txt"), "w") as f:
                f.write("should not be found\n")

        # Create ignored files at root level
        for fname in ignored_files:
            with open(os.path.join(root, fname), "w") as f:
                f.write("SECRET=value\n")

        # Create a legitimate file that SHOULD be discovered
        legit_path = os.path.join(root, "legit.txt")
        with open(legit_path, "w") as f:
            f.write("hello world\n")

        result = scanner.discover_files(root)

        # None of the ignored dir names should appear as a path component
        for path in result:
            rel = os.path.relpath(path, root)
            parts = rel.split(os.sep)
            for ignored_dir in ignored_dirs:
                assert ignored_dir not in parts, (
                    f"Ignored dir '{ignored_dir}' found in discovered path: {path}"
                )

        # None of the ignored file names should appear in results
        result_basenames = {os.path.basename(p) for p in result}
        for fname in ignored_files:
            assert fname not in result_basenames, (
                f"Ignored file '{fname}' was discovered: {fname}"
            )

        # The legitimate file must be present
        assert legit_path in result, "Legitimate file was not discovered"


@given(
    swap_suffix=st.sampled_from([".swp", "~"]),
    base_name=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
        min_size=1,
        max_size=20,
    ),
)
@settings(max_examples=100)
def test_swap_files_not_discovered(swap_suffix, base_name):
    """
    **Validates: Requirements 2.2**

    Swap files (*.swp, *~) must not appear in discover_files results.
    """
    scanner = FileScanner()

    with tempfile.TemporaryDirectory() as root:
        if swap_suffix == "~":
            swap_name = base_name + "~"
        else:
            swap_name = base_name + swap_suffix

        swap_path = os.path.join(root, swap_name)
        with open(swap_path, "w") as f:
            f.write("swap content\n")

        # Also create a legit file
        legit_path = os.path.join(root, "legit.txt")
        with open(legit_path, "w") as f:
            f.write("hello\n")

        result = scanner.discover_files(root)

        assert swap_path not in result, f"Swap file '{swap_name}' should not be discovered"
        assert legit_path in result, "Legitimate file was not discovered"


def test_binary_files_not_discovered():
    """
    **Validates: Requirements 2.3**

    Binary files (non-UTF-8 decodable) must not appear in discover_files results.
    """
    scanner = FileScanner()

    with tempfile.TemporaryDirectory() as root:
        # Write a binary file with non-UTF-8 bytes
        binary_path = os.path.join(root, "image.bin")
        with open(binary_path, "wb") as f:
            f.write(bytes(range(256)))

        # Write a valid UTF-8 file
        text_path = os.path.join(root, "readme.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write("hello world\n")

        result = scanner.discover_files(root)

        assert binary_path not in result, "Binary file should not be discovered"
        assert text_path in result, "Text file should be discovered"


# ---------------------------------------------------------------------------
# Helpers for task-5 tests
# ---------------------------------------------------------------------------

import sys
import json
from unittest.mock import patch, MagicMock
from hypothesis import HealthCheck
from argos import ScanSummary, load_cache, save_cache


# ---------------------------------------------------------------------------
# Property 1: Invalid path produces error output
# Feature: jules-cli-scan, Property 1: Invalid path produces error output
# Validates: Requirements 1.3
# ---------------------------------------------------------------------------

@given(
    suffix=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=100, deadline=None)
def test_invalid_path_produces_error(suffix):
    """
    **Validates: Requirements 1.3**

    For any string that does not correspond to an existing directory,
    run_scan must exit with a non-zero code and print an error message.
    """
    from argos import run_scan

    with tempfile.TemporaryDirectory() as root:
        non_existent = os.path.join(root, f"does_not_exist_{suffix}")
        with pytest.raises(SystemExit) as exc_info:
            run_scan(non_existent)
        assert exc_info.value.code != 0


@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=100)
def test_file_path_not_directory_produces_error(filename):
    """
    **Validates: Requirements 1.3**

    Passing a file path (not a directory) must also exit with non-zero code.
    """
    from argos import run_scan

    with tempfile.TemporaryDirectory() as root:
        file_path = os.path.join(root, filename + ".txt")
        with open(file_path, "w") as f:
            f.write("hello")
        with pytest.raises(SystemExit) as exc_info:
            run_scan(file_path)
        assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# Property 11: Missing required env vars produce error before scanning
# Feature: jules-cli-scan, Property 11: Missing required env vars produce error before scanning
# Validates: Requirements 8.2, 8.3
# ---------------------------------------------------------------------------

@given(
    missing=st.sampled_from([
        ("GROQ_API_KEY",),
        ("OBSIDIAN_INBOX_URL",),
        ("GROQ_API_KEY", "OBSIDIAN_INBOX_URL"),
    ])
)
@settings(max_examples=100)
def test_missing_env_vars_produce_error_before_scanning(missing):
    """
    **Validates: Requirements 8.2, 8.3**

    When GROQ_API_KEY or OBSIDIAN_INBOX_URL are not defined, run_scan must
    exit with non-zero code without scanning any files.
    """
    from argos import run_scan

    with tempfile.TemporaryDirectory() as root:
        # Create a valid directory with a file so scanning would happen if env vars were present
        with open(os.path.join(root, "file.txt"), "w") as f:
            f.write("# @argos test\n")

        original_get = os.environ.get

        def patched_get(key, default=None):
            if key in missing:
                return ""
            return original_get(key, default)

        scanner_calls = []

        with patch("os.environ.get", side_effect=patched_get):
            with patch("argos.FileScanner.run", side_effect=lambda *a, **kw: scanner_calls.append(a)):
                with pytest.raises(SystemExit) as exc_info:
                    run_scan(root)

        assert exc_info.value.code != 0
        assert len(scanner_calls) == 0, "FileScanner.run should not be called when env vars are missing"


# ---------------------------------------------------------------------------
# Property 9: Summary counts are accurate
# Feature: jules-cli-scan, Property 9: Summary counts are accurate
# Validates: Requirements 7.4
# ---------------------------------------------------------------------------

@given(
    created=st.integers(min_value=0, max_value=5),
    skipped=st.integers(min_value=0, max_value=5),
    errors=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=100)
def test_summary_counts_match_accumulated_results(created, skipped, errors):
    """
    **Validates: Requirements 7.4**

    The summary printed at the end must match the accumulated counters from
    all scan_file results.
    """
    from argos import FileScanner, ScanResult

    scanner = FileScanner()

    total_files = max(created + skipped + errors, 1)

    with tempfile.TemporaryDirectory() as root:
        files = []
        for i in range(total_files):
            fp = os.path.join(root, f"file_{i}.txt")
            with open(fp, "w") as f:
                f.write("hello\n")
            files.append(fp)

        # Build fake results: distribute created/skipped/errors across files
        fake_results = []
        c, s, e = created, skipped, errors
        for _ in files:
            nc = min(c, 1)
            ns = min(s, 1)
            ne = min(e, 1)
            fake_results.append(ScanResult(
                filepath="x",
                triggers_found=nc + ns + ne,
                notes_created=nc,
                triggers_skipped=ns,
                errors=ne,
            ))
            c -= nc; s -= ns; e -= ne

        call_idx = [0]

        def fake_scan_file(filepath, cache):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx < len(fake_results):
                return fake_results[idx]
            return ScanResult(filepath=filepath, triggers_found=0, notes_created=0, triggers_skipped=0, errors=0)

        with patch.object(scanner, "discover_files", return_value=files):
            with patch.object(scanner, "scan_file", side_effect=fake_scan_file):
                summary = scanner.run(root)

    expected_created = sum(r.notes_created for r in fake_results)
    expected_skipped = sum(r.triggers_skipped for r in fake_results)
    expected_errors = sum(r.errors for r in fake_results)

    assert summary.files_scanned == len(files)
    assert summary.notes_created == expected_created
    assert summary.triggers_skipped == expected_skipped
    assert summary.errors == expected_errors


# ---------------------------------------------------------------------------
# Property 10: Exit code reflects errors
# Feature: jules-cli-scan, Property 10: Exit code reflects errors
# Validates: Requirements 7.5
# ---------------------------------------------------------------------------

@given(error_count=st.integers(min_value=0, max_value=20))
@settings(max_examples=100)
def test_exit_code_reflects_errors(error_count):
    """
    **Validates: Requirements 7.5**

    If summary.errors > 0, process must exit with code 1.
    If summary.errors == 0, process must exit with code 0.
    """
    from argos import run_scan, ScanSummary

    fake_summary = ScanSummary(
        files_scanned=1,
        triggers_found=error_count,
        notes_created=0,
        triggers_skipped=0,
        errors=error_count,
    )

    env = {"GROQ_API_KEY": "key", "OBSIDIAN_INBOX_URL": "http://localhost"}

    with tempfile.TemporaryDirectory() as root:
        with patch("os.environ.get", side_effect=lambda k, d=None: env.get(k, d)):
            with patch("argos.FileScanner.run", return_value=fake_summary):
                with pytest.raises(SystemExit) as exc_info:
                    run_scan(root)

    expected_code = 1 if error_count > 0 else 0
    assert exc_info.value.code == expected_code


# ---------------------------------------------------------------------------
# Property 8: Progress output contains file paths and trigger confirmations
# Feature: jules-cli-scan, Property 8: Progress output contains file paths
# Validates: Requirements 7.1, 7.2, 7.3
# ---------------------------------------------------------------------------

@given(n_files=st.integers(min_value=1, max_value=5))
@settings(max_examples=50)
def test_progress_output_contains_file_paths(n_files):
    """
    **Validates: Requirements 7.1, 7.2, 7.3**

    For any scan execution over a directory with eligible files, the printed
    output must contain the path of each file being processed.
    """
    import io
    from argos import FileScanner, ScanResult

    scanner = FileScanner()

    with tempfile.TemporaryDirectory() as root:
        files = []
        for i in range(n_files):
            fp = os.path.join(root, f"file_{i}.txt")
            with open(fp, "w") as f:
                f.write("hello\n")
            files.append(fp)

        def fake_scan_file(filepath, cache):
            return ScanResult(filepath=filepath, triggers_found=0, notes_created=0, triggers_skipped=0, errors=0)

        captured_output = io.StringIO()
        with patch.object(scanner, "discover_files", return_value=files):
            with patch.object(scanner, "scan_file", side_effect=fake_scan_file):
                with patch("sys.stdout", captured_output):
                    scanner.run(root)

        output = captured_output.getvalue()

        for filepath in files:
            assert filepath in output, f"File path '{filepath}' not found in progress output"


# ---------------------------------------------------------------------------
# Unit tests — Tarea 7
# ---------------------------------------------------------------------------

# Test 1: --help imprime uso y sale con código 0 (Req 1.4)
def test_help_flag_exits_zero():
    """
    Validates: Requirements 1.4

    `jules --help` debe imprimir el uso y salir con código 0.
    """
    import subprocess
    result = subprocess.run(
        [sys.executable, "argos.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "argos" in result.stdout.lower()


# Test 2: Directorio vacío → mensaje informativo + exit 0 (Req 2.4)
def test_empty_directory_exits_zero(tmp_path, monkeypatch):
    """
    Validates: Requirements 2.4

    Cuando no hay archivos elegibles, run_scan debe imprimir un mensaje
    informativo y salir con código 0.
    """
    from argos import run_scan

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("OBSIDIAN_INBOX_URL", "http://localhost")

    with pytest.raises(SystemExit) as exc_info:
        run_scan(str(tmp_path))

    assert exc_info.value.code == 0


# Test 3: Caché ausente → se crea tras primer write exitoso (Req 4.4)
def test_cache_created_on_first_write(tmp_path):
    """
    Validates: Requirements 4.4

    Si el archivo de caché no existe, save_cache debe crearlo al primer write.
    """
    from argos import save_cache

    cache_path = tmp_path / "test_cache.json"
    assert not cache_path.exists()

    with patch("argos.CACHE_FILE", str(cache_path)):
        save_cache({"abc123": {"timestamp": 1.0, "filepath": "f.py", "comment": "# @argos"}})

    assert cache_path.exists()
    with open(cache_path, "r") as f:
        data = json.load(f)
    assert "abc123" in data


# Test 4: Variables de entorno cargadas correctamente desde .env (Req 8.1)
def test_dotenv_loads_groq_api_key(tmp_path, monkeypatch):
    """
    Validates: Requirements 8.1

    load_dotenv debe cargar GROQ_API_KEY desde el archivo .env.
    """
    from dotenv import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=test-secret-key\n")

    # Asegurarse de que la variable no está en el entorno antes de cargar
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    load_dotenv(dotenv_path=str(env_file), override=True)

    assert os.environ.get("GROQ_API_KEY") == "test-secret-key"
