import importlib.resources as res
import os
import platform
import shutil
import subprocess
import sys


def add_executable_permissions(path):
    if is_executable(path):
        return path
    
    current_permissions = os.stat(path).st_mode
    new_permissions = current_permissions | 0o111
    os.chmod(path, new_permissions)


def find_package(package) -> str | None:
    return shutil.which(package)


def get_env(key, default = None):
    return os.getenv(key, default)


def get_mac_version():
    return platform.mac_ver()


def get_nodename():
    return platform.node()


def get_platform():
    return platform.system().lower()


def get_project_path(path):
    return res.files("src").joinpath(path)


def is_executable(path):
    return os.access(path, os.X_OK)


def run_process(cmd):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
        env=os.environ.copy(),
    )
