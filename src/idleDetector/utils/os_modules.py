import os
import shutil
import subprocess
import sys


def find_package(package) -> str | None:
    return shutil.which(package)


def get_env(key, default: str = "") -> str | None:
    return os.getenv(key, default)


def get_platform():
    return sys.platform.lower()


def run_process(cmd):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        text=True,
        check=True,
        env=os.environ.copy(),
    )
