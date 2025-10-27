import importlib.resources as res
import os
import platform
import shutil
import subprocess


def add_executable_permissions(path):
    if is_executable(path):
        return path

    current_permissions = os.stat(path).st_mode
    new_permissions = current_permissions | 0o111
    os.chmod(path, new_permissions)


def find_package(package, default=None):
    return shutil.which(package) or default


def get_env(key, default=None):
    return os.getenv(key, default)


def get_mac_version():
    return platform.mac_ver()


def get_nodename():
    return platform.node()


def get_sys_path():
    return os.environ["PATH"]


def get_platform():
    return platform.system().lower()


def get_project_path(path):
    return res.files("idle_detector").joinpath(path)


def getuid():
    return os.getuid()


def is_executable(path):
    return os.access(path, os.X_OK)


def is_file(fp):
    return os.path.isfile(fp)


def copy_file(src, dst):
    shutil.copy(src, dst)


def rename(src, dst):
    os.rename(src, dst)


def rm_file(fp):
    if is_file(fp):
        os.remove(fp)


def run_process(cmd, **kwargs):
    default_kwargs = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
        env=os.environ.copy(),
    )
    default_kwargs.update(**kwargs)
    return subprocess.run(cmd, **default_kwargs)


def terminate(status=0):
    os._exit(status)


__all__ = (
    "add_executable_permissions",
    "find_package",
    "get_env",
    "get_mac_version",
    "get_nodename",
    "get_platform",
    "get_project_path",
    "is_executable",
    "is_file",
    "rename",
    "rm_file",
    "run_process",
    "terminate",
)
