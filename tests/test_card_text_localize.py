"""Execute the shared card-text localizer's browser-side contract."""

import shutil
import subprocess

import pytest


def test_card_text_localize_runtime() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    result = subprocess.run(
        [node, "--test", "tests/js/text-localize.test.mjs"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
