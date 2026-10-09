"""Shared fixtures."""

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sg01lp1_raw() -> dict[str, Any]:
    """Register snapshot from a 3.6K-SG01LP1 (serial number replaced)."""
    return json.loads((FIXTURES / "sg01lp1_3k6.json").read_text())
