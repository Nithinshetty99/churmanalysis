"""Smoke-test the Streamlit app headlessly. Needs outputs/ from a pipeline run."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "outputs" / "summary.json").exists(),
                                reason="run `python -m churn_platform.pipeline` first")


def test_dashboard_renders_without_exceptions():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 6
    assert len(at.metric) >= 4


def test_campaign_sliders_update_without_error():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=90).run()
    sliders = [s for s in at.slider if "Save rate" in s.label]
    assert sliders, "save-rate slider not found"
    sliders[0].set_value(0.30).run()
    assert not at.exception, [e.value for e in at.exception]
