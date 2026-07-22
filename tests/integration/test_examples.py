"""Smoke tests for the runnable examples in ``examples/``.

Each example is imported with ``examples/`` on ``sys.path`` (they import the
shared ``_data`` helper), executed via its ``main()``, and checked for the
key output markers documented in ``examples/README.md``. Datasets are seeded,
so the markers are deterministic.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture()
def examples_path():
    sys.path.insert(0, str(EXAMPLES_DIR))
    try:
        yield
    finally:
        sys.path.remove(str(EXAMPLES_DIR))
        for name in (
            "_data",
            "basic_analysis",
            "full_stack",
            "chart_payload",
            "ai_analysis_mock",
            "backtest_smc",
        ):
            sys.modules.pop(name, None)


def _run(module_name: str, capsys, **kwargs):
    module = importlib.import_module(module_name)
    module.main(**kwargs)
    return capsys.readouterr().out


@pytest.mark.usefixtures("examples_path")
def test_basic_analysis(capsys):
    out = _run("basic_analysis", capsys)
    assert "structure:" in out
    assert "liquidity:" in out
    assert "fvg:" in out
    assert "first swing:" in out


@pytest.mark.usefixtures("examples_path")
def test_full_stack(capsys):
    out = _run("full_stack", capsys)
    assert "full stack over 300 bars" in out
    assert "confluence" in out
    assert "bias:" in out


@pytest.mark.usefixtures("examples_path")
def test_chart_payload(capsys, tmp_path):
    out = _run("chart_payload", capsys, out_dir=tmp_path)
    assert "layers" in out
    written = tmp_path / "chart_payload.json"
    assert written.exists()
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert len(payload["payload"]["layers"]) == 23


@pytest.mark.usefixtures("examples_path")
def test_ai_analysis_mock(capsys):
    out = _run("ai_analysis_mock", capsys)
    assert "ai report:" in out
    assert "bias:" in out
    assert "weaknesses (mandatory):" in out


@pytest.mark.usefixtures("examples_path")
def test_backtest_smc(capsys):
    out = _run("backtest_smc", capsys)
    assert "backtest: smc_pullback" in out
    assert "trades" in out
    assert "win_rate" in out
    assert "take_profit" in out
