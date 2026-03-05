"""
Test FLOKx removal — ensures no active code references FLOKx.

This is a regression guard: if anyone accidentally re-introduces FLOKx,
this test fails immediately.
"""

import os
import re
import pytest

# Directories/files to scan (active code only, not docs/archive)
SCAN_DIRS = [
    os.path.join(os.path.dirname(__file__), '..', 'backend'),
    os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src'),
    os.path.join(os.path.dirname(__file__)),  # tests dir itself
]

# Allowed exceptions: docs, archive, and this test file itself
SKIP_PATTERNS = [
    '/docs/', '/archive/', '/_archive/', '/_reports/',
    'test_flokx_removal.py',  # This file referencing the pattern is expected
    '.md',
    'node_modules/',
    '__pycache__/',
    '.git/',
]

FLOKX_PATTERN = re.compile(r'flokx', re.IGNORECASE)


def _should_skip(filepath: str) -> bool:
    for pat in SKIP_PATTERNS:
        if pat in filepath:
            return True
    return False


def _scan_for_flokx():
    """Walk active code directories and find any FLOKx references."""
    hits = []
    for scan_dir in SCAN_DIRS:
        abs_dir = os.path.abspath(scan_dir)
        if not os.path.isdir(abs_dir):
            continue
        for root, dirs, files in os.walk(abs_dir):
            # Skip hidden/cache dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules' and d != '__pycache__']
            for fname in files:
                if not fname.endswith(('.py', '.js', '.jsx', '.ts', '.tsx', '.sh', '.env')):
                    continue
                filepath = os.path.join(root, fname)
                if _should_skip(filepath):
                    continue
                try:
                    with open(filepath, 'r', errors='ignore') as f:
                        for lineno, line in enumerate(f, 1):
                            if FLOKX_PATTERN.search(line):
                                hits.append(f"{filepath}:{lineno}: {line.strip()}")
                except Exception:
                    continue
    return hits


class TestFLOKxRemoval:
    """Verify FLOKx is completely removed from active code."""

    def test_no_flokx_in_backend(self):
        """Backend must not reference FLOKx in any active code file."""
        hits = _scan_for_flokx()
        backend_hits = [h for h in hits if '/backend/' in h]
        assert len(backend_hits) == 0, (
            f"FLOKx references found in backend:\n" + "\n".join(backend_hits)
        )

    def test_no_flokx_in_frontend(self):
        """Frontend must not reference FLOKx in any active code file."""
        hits = _scan_for_flokx()
        frontend_hits = [h for h in hits if '/frontend/' in h]
        assert len(frontend_hits) == 0, (
            f"FLOKx references found in frontend:\n" + "\n".join(frontend_hits)
        )

    def test_no_flokx_in_tests(self):
        """Tests must not reference FLOKx except this guard test."""
        hits = _scan_for_flokx()
        test_hits = [h for h in hits if '/tests/' in h and 'test_flokx_removal' not in h]
        assert len(test_hits) == 0, (
            f"FLOKx references found in tests:\n" + "\n".join(test_hits)
        )

    def test_flokx_integration_file_deleted(self):
        """backend/flokx_integration.py must not exist."""
        path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'flokx_integration.py')
        assert not os.path.exists(path), "backend/flokx_integration.py still exists"

    def test_flokx_alerts_section_deleted(self):
        """FlokxAlertsSection.js must not exist."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'pages',
            'dashboard', 'sections', 'FlokxAlertsSection.js'
        )
        assert not os.path.exists(path), "FlokxAlertsSection.js still exists"
