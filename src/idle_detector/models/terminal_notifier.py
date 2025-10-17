from functools import cached_property
from itertools import chain
from pathlib import Path

from ..utils.common import (
    compare_versions,
    date_parser,
    encode_message,
    run_async_process,
)
from ..utils.exceptions import MissingPackage
from ..utils.os_modules import (
    add_executable_permissions,
    find_package,
    get_project_path,
    is_executable,
)
from ._dataclasses import GroupTypes, NotifierFlags, SerializedNamespace


class TerminalNotifier:
    CURRENT_VERSION = (2, 0, 0)
    MINIMUM_COMPATIBLE_VERSION = (1, 8, 0)
    PACKAGE_NAME = "terminal-notifier"

    group_types: GroupTypes = GroupTypes

    async def check_notifier(self):
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

        tn_version = await self.version
        tn_version_tuple = tuple(int(v) for v in tn_version.split("."))
        await compare_versions(self, tn_version_tuple)

    async def notify(self, **terminal_notifier_kwargs):
        test_message = "This is a test notification from idle-detector."
        message = terminal_notifier_kwargs.pop("message", test_message)
        msg_command = (NotifierFlags.MESSAGE.flag, encode_message(message))
        arg_commands = (
            # --flag <value>
            (NotifierFlags[k.upper()].flag, str(v))
            for k, v in terminal_notifier_kwargs.items()
            if NotifierFlags.is_flag_available(k)
        )
        full_command = chain.from_iterable((msg_command, *arg_commands))

        await self.execute_command(full_command)

    async def execute_command(self, cmd):
        tn_cmd = (self.terminal_notifier_bin, *cmd)
        return await run_async_process(tn_cmd)

    async def clear_notifications_by_group(self, *, group_type: GroupTypes):
        await self.execute_command(["-remove", group_type])

    async def clear_all_notifications(self):
        await self.clear_notifications_by_group(group_type="ALL")

    async def list_notifications(self):
        process = await self.execute_command([NotifierFlags.LIST.flag, "ALL"])

        header_field_names = ("group", "title", "subtitle", "message", "delivered_at")
        notifications = []

        for line in process.stdout.splitlines()[1:]:
            line = line.split("\t")
            notifications.append(dict(zip(header_field_names, line, strict=True)))

            try:
                notifications[-1]["delivered_at"] = date_parser(
                    notifications[-1]["delivered_at"]
                )
            except ValueError:
                pass

        return notifications

    async def count_notifications(self):
        all_notifications = await self.list_notifications()
        return len(all_notifications)

    @cached_property
    async def version(self):
        process = await self.execute_command(["-version"])
        # output: terminal-notifier <version>.
        tn_version = process.stdout.split()
        return tn_version[1].rstrip(".")

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
