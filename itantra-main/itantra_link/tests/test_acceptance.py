"""
Lets pytest (and CI) run the script-style acceptance tests. Each runs in its own
process because they use fixed UDP ports, module globals and SystemExit.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPTS = [
    "itantra_link.tests.test_link",
    "itantra_link.tests.test_channel",
    "itantra_link.tests.test_queue",
    "itantra_ai.tests.test_model_packs",
]


@pytest.mark.parametrize("module", SCRIPTS)
def test_script(module):
    r = subprocess.run([sys.executable, "-m", module], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=400)
    assert r.returncode == 0, f"{module} failed:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}"
