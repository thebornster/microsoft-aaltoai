"""Gate 5: outside RAJA_DEMO_MODE=1, a missing required secret must fail
closed at startup, not silently fall back to a well-known demo default.

The subprocess tests are necessary (not just unit tests of gateway.env)
because gateway/instance.py and approval/app.py compute their secrets once
at import time as module-level constants; re-importing an already-imported
module in this same process would not re-run that code. A clean subprocess
is the only way to observe real startup behavior.
"""
import subprocess
import sys

import pytest

from gateway.env import ConfigError, is_demo_mode, require_secret


def test_require_secret_uses_env_value_when_set(monkeypatch):
    monkeypatch.setenv("RAJA_TEST_SECRET", "real-value")
    assert require_secret("RAJA_TEST_SECRET", "insecure-default") == "real-value"


def test_require_secret_fails_closed_without_demo_mode(monkeypatch):
    monkeypatch.delenv("RAJA_TEST_SECRET", raising=False)
    monkeypatch.delenv("RAJA_DEMO_MODE", raising=False)
    with pytest.raises(ConfigError):
        require_secret("RAJA_TEST_SECRET", "insecure-default")


def test_require_secret_allows_default_under_demo_mode(monkeypatch):
    monkeypatch.delenv("RAJA_TEST_SECRET", raising=False)
    monkeypatch.setenv("RAJA_DEMO_MODE", "1")
    assert require_secret("RAJA_TEST_SECRET", "insecure-default") == "insecure-default"


def test_is_demo_mode_requires_exact_value(monkeypatch):
    monkeypatch.setenv("RAJA_DEMO_MODE", "true")
    assert is_demo_mode() is False
    monkeypatch.setenv("RAJA_DEMO_MODE", "1")
    assert is_demo_mode() is True


def _run_import(module: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=str(__import__("pathlib").Path(__file__).parent.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_gateway_instance_import_fails_closed_without_demo_mode(monkeypatch, tmp_path):
    import os

    env = {k: v for k, v in os.environ.items() if k not in ("RAJA_DEMO_MODE", "RAJA_SERVER_KEY")}
    result = _run_import("gateway.instance", env)
    assert result.returncode != 0
    assert "RAJA_SERVER_KEY" in result.stderr


def test_gateway_instance_import_succeeds_under_demo_mode(tmp_path):
    import os

    env = {k: v for k, v in os.environ.items() if k not in ("RAJA_DEMO_MODE", "RAJA_SERVER_KEY")}
    env["RAJA_DEMO_MODE"] = "1"
    result = _run_import("gateway.instance", env)
    assert result.returncode == 0, result.stderr


def test_gateway_instance_import_succeeds_with_real_key_no_demo_mode(tmp_path):
    import os

    env = {k: v for k, v in os.environ.items() if k not in ("RAJA_DEMO_MODE", "RAJA_SERVER_KEY")}
    env["RAJA_SERVER_KEY"] = "a-real-production-key"
    result = _run_import("gateway.instance", env)
    assert result.returncode == 0, result.stderr
