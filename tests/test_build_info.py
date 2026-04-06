"""
Unit tests for backend/routes/build_info.py

Verifies that git metadata (sha, branch) resolves correctly even when the
process working directory is not the repo root.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_git_sha_not_unknown_when_dot_git_exists():
    """SHA must be a real commit hash, not 'unknown', when .git is present."""
    from routes.build_info import get_git_sha, _REPO_ROOT
    # Only run the assertion when .git actually exists (i.e. in the repo)
    if not (_REPO_ROOT / '.git').exists():
        import pytest
        pytest.skip(".git directory not present – skipping git-dependent test")

    original_cwd = os.getcwd()
    try:
        os.chdir('/tmp')  # simulate uvicorn started outside repo root
        sha = get_git_sha()
    finally:
        os.chdir(original_cwd)

    assert sha != "unknown", f"Expected a real git SHA but got 'unknown' (cwd was /tmp)"
    assert len(sha) >= 7, f"Git SHA looks too short: {sha!r}"


def test_git_branch_not_unknown_when_dot_git_exists():
    """Branch must be a real name, not 'unknown', when .git is present."""
    from routes.build_info import get_git_branch, _REPO_ROOT
    if not (_REPO_ROOT / '.git').exists():
        import pytest
        pytest.skip(".git directory not present – skipping git-dependent test")

    original_cwd = os.getcwd()
    try:
        os.chdir('/tmp')
        branch = get_git_branch()
    finally:
        os.chdir(original_cwd)

    assert branch != "unknown", f"Expected a real git branch but got 'unknown' (cwd was /tmp)"


def test_deployment_host_not_loopback():
    """_get_deployment_host() must never return a loopback address."""
    import importlib
    import unittest.mock as mock

    # Simulate the systemd env: HOST=127.0.0.1, no HOSTNAME
    env_patch = {"HOST": "127.0.0.1"}
    with mock.patch.dict(os.environ, env_patch, clear=False):
        # Remove HOSTNAME if set so we hit the loopback branch
        os.environ.pop("HOSTNAME", None)
        # Re-import to pick up patched env (function reads env at call-time)
        import routes.build_info as bi
        host = bi._get_deployment_host()

    assert host not in {"127.0.0.1", "localhost", "::1"}, (
        f"deployment.host should not be a loopback address, got: {host!r}"
    )
