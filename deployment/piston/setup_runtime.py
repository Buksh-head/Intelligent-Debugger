"""Prepares the Piston Python runtime for student submissions (issue #117).
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PISTON_URL = os.environ.get("PISTON_URL", "http://piston:2000")
PYTHON_VERSION = os.environ.get("PISTON_PYTHON_VERSION", "3.12.0")
# Shared with the piston service through the piston-packages volume.
RUNTIME_DIR = Path("/piston/packages/python") / PYTHON_VERSION
REQUIREMENTS = Path(__file__).resolve().parent / "requirements.txt"

# numpy's OpenBLAS starts one busy thread per host core on import, which alone
# uses most of Piston's 3 second CPU limit and makes plotting code time out.
# Piston passes each line of the runtime's .env file to every job.
RUNTIME_ENV = {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}

SMOKE_CHECK_SOURCE = """\
import os

import numpy as np
import matplotlib.pyplot as plt

plt.plot(np.arange(4))
plt.savefig("smoke.png")
print("modules ok", int(np.arange(4).sum()), os.environ.get("OPENBLAS_NUM_THREADS"))
"""
SMOKE_CHECK_STDOUT = "modules ok 6 1"


def _request(path, payload=None, timeout=30.0):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        PISTON_URL + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def wait_for_piston(attempts=60, delay=2.0):
    for _ in range(attempts):
        try:
            return _request("/api/v2/runtimes", timeout=5.0)
        except (urllib.error.URLError, OSError):
            time.sleep(delay)
    sys.exit("Piston did not become reachable at {}".format(PISTON_URL))


def ensure_python_runtime(runtimes):
    installed = any(
        runtime["language"] == "python" and runtime["version"] == PYTHON_VERSION
        for runtime in runtimes
    )
    if installed:
        print("Python {} runtime already installed".format(PYTHON_VERSION), flush=True)
        return
    print("Installing Python {} runtime into Piston".format(PYTHON_VERSION), flush=True)
    _request(
        "/api/v2/packages",
        {"language": "python", "version": PYTHON_VERSION},
        timeout=900.0,
    )


def install_modules():
    print("Installing Python modules from {}".format(REQUIREMENTS.name), flush=True)
    subprocess.run(
        [
            str(RUNTIME_DIR / "bin" / "python3"),
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "--root-user-action=ignore",
            "-r",
            str(REQUIREMENTS),
        ],
        check=True,
    )


def configure_runtime_env():
    env_file = RUNTIME_DIR / ".env"
    lines = env_file.read_text().splitlines()
    missing = [
        "{}={}".format(name, value)
        for name, value in RUNTIME_ENV.items()
        if "{}={}".format(name, value) not in lines
    ]
    if missing:
        env_file.write_text("\n".join(lines + missing) + "\n")


def smoke_check():
    run = _request(
        "/api/v2/execute",
        {
            "language": "python",
            "version": PYTHON_VERSION,
            "files": [{"content": SMOKE_CHECK_SOURCE}],
        },
    )["run"]
    if run["code"] != 0 or run["stdout"].strip() != SMOKE_CHECK_STDOUT:
        # Piston caches a runtime's .env on its first job, so a Piston that was
        # already serving jobs needs a restart to pick up RUNTIME_ENV.
        sys.exit(
            "Piston smoke check failed: {}\nIf Piston was already running before "
            "this setup, run `docker compose restart piston` and then "
            "`docker compose up` again.".format(json.dumps(run, indent=2))
        )
    print("Piston smoke check passed: {}".format(run["stdout"].strip()), flush=True)
    if run["stderr"]:
        print("smoke check stderr:\n{}".format(run["stderr"]), flush=True)


def main():
    ensure_python_runtime(wait_for_piston())
    install_modules()
    configure_runtime_env()
    smoke_check()


if __name__ == "__main__":
    main()