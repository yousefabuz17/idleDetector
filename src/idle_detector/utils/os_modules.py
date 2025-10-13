import importlib.resources as res
import os
import platform
import shutil
import subprocess

from ..utils.common import PathLike


def add_executable_permissions(path) -> PathLike | None:
    if is_executable(path):
        return path

    current_permissions = os.stat(path).st_mode
    new_permissions = current_permissions | 0o111
    os.chmod(path, new_permissions)


def find_package(package) -> PathLike | None:
    return shutil.which(package)


def get_env(key, default=None):
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


def is_file(fp):
    return os.path.isfile(fp)


def rename(src, dst):
    os.rename(src, dst)


def rm_file(fp):
    if is_file(fp):
        os.remove(fp)


def rm_files(*files):
    for f in files:
        rm_file(f)


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
