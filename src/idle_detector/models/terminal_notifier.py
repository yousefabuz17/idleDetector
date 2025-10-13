from functools import cached_property
from itertools import chain
from pathlib import Path

from dateutil.parser import parse as date_parser

from ..utils.common import encode_message, regex_search
from ..utils.exceptions import MissingPackage
from ..utils.os_modules import (
    add_executable_permissions,
    find_package,
    get_project_path,
    is_executable,
    run_process,
)
from ._dataclasses import GroupTypes, NotifierFlags, SerializedNamespace


class TerminalNotifier:
    CURRENT_VERSION = (2, 0, 0)
    PACKAGE_NAME = "terminal-notifier"
    TEST_MESSAGE = "This is a test notification from idle-detector."

    def check_notifier(self):
        tn_bin = self.terminal_notifier_bin

        if not tn_bin:
            pkg_name = self.PACKAGE_NAME
            raise MissingPackage(
                f"Required package {pkg_name!r} was not found in the system PATH. "
                f"Please ensure {pkg_name!r} is installed and accessible in your environment.",
            )

        add_executable_permissions(tn_bin)

        if not is_executable(tn_bin):
            raise Exception(
                f"The {tn_bin} binary is not executable. Please check its permissions."
            )

    def notify(self, message=None, **kwargs):
        msg_command = (
            NotifierFlags.MESSAGE.flag,
            encode_message(message or self.TEST_MESSAGE),
        )
        arg_commands = (
            (NotifierFlags[k.upper()].flag, str(v))
            for k, v in kwargs.items()
            if NotifierFlags.is_flag_available(k)
        )
        full_command = chain.from_iterable((msg_command, *arg_commands))
        self.execute_command(full_command)

    def execute_command(self, cmd):
        cmd = (self.terminal_notifier_bin, *cmd)
        return run_process(cmd)

    def clear_notifications_by_stage(self, *, group_type: GroupTypes | str):
        if isinstance(group_type, GroupTypes):
            group_type = group_type.value
        return self.execute_command(["-remove", group_type])

    def clear_all_notifications(self):
        return self.clear_notifications_by_stage(group_type="ALL")

    def list_notifications(self):
        process = self.execute_command([NotifierFlags.LIST.flag, "ALL"])

        header_field_names = ("group", "title", "subtitle", "message", "delivered_at")
        notifications = []

        for line in process.stdout.splitlines()[1:]:
            line = line.split("\t")
            notifications.append(dict(zip(header_field_names, line, strict=False)))

            try:
                notifications[-1]["delivered_at"] = date_parser(
                    notifications[-1]["delivered_at"]
                )
            except ValueError:
                pass

        return notifications

    def count_notifications(self):
        return len(self.list_notifications())

    @cached_property
    def version(self):
        process = self.execute_command(["-version"])
        tn_version = regex_search(r"(\d\.?){1,3}", process.stdout)
        if tn_version:
            tn_version = tn_version.group().rstrip(".")
        else:
            tn_version = ".".join(self.CURRENT_VERSION)
        return tn_version

    @cached_property
    def content_images(self):
        idle_images = Path(self.assets_path).glob("*.png")
        return SerializedNamespace(module="Assets", **{p.stem: p for p in idle_images})

    @cached_property
    def assets_path(self):
        return get_project_path("idle_detector/assets")

    @cached_property
    def terminal_notifier_bin(self):
        return find_package(self.PACKAGE_NAME)
