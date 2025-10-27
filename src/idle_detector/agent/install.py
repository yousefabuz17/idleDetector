from dataclasses import dataclass
from functools import cached_property, wraps

from ..utils.common import type_name
from ..utils.exceptions import MissingPackage
from ..utils.os_modules import (
    find_package,
    getuid,
    run_process,
)
from .generate import AgentGenerator


def agent_must_exist(func):
    @wraps(func)
    def wrapper(self):
        if not self.agent_file_exists():
            raise FileNotFoundError(
                f"The agent file does not exist at: {self.agent_file.as_posix()}"
            )
        return func(self)

    return wrapper


def safeguard_check(must_be_booted: bool = False):
    def decorator(func):
        @wraps(func)
        def wrapper(self):
            self.check_core()

            already_booted = self.is_booted_already
            conditions_met = (must_be_booted and already_booted) or (
                not must_be_booted and not already_booted
            )
            if conditions_met:
                return func(self)

        return wrapper

    return decorator


@dataclass(init=False)
class AgentInstaller(AgentGenerator):
    """
    Manages installation, registration, and lifecycle control of a macOS LaunchAgent.

    This class provides methods to bootstrap, enable, disable, start, or remove
    a LaunchAgent via the `launchctl` system utility. It encapsulates the necessary
    file operations and process calls to manage a `.plist` agent file under the
    user's `~/Library/LaunchAgents` directory.

    The default agent label is `com.github.idleDetector`, and its associated plist
    file is expected to be located relative to the project directory.
    """

    def __str__(self):
        """Return a concise string representation of the AgentInstaller instance."""
        return "{}(label={!r}, agent_file={!r})".format(
            type_name(self), self.AGENT_LABEL, self.agent_file
        )

    def __boot_agent(self, bootout: bool = False):
        """
        Bootstrap or bootout the LaunchAgent.

        Args:
            bootout (bool): If True, deregisters the agent (`bootout`).
                If False, registers it (`bootstrap`).

        Returns:
            subprocess.CompletedProcess: The result of the `launchctl` command.
        """
        boot_type = "bootout" if bootout else "bootstrap"
        cmd = [boot_type, self.guid, self.agent_file.as_posix()]
        return self.execute_launchctl(cmd)

    def __control_agent(self, *, disable: bool = False, start: bool = False):
        """
        Control the state of a registered LaunchAgent.

        Args:
            disable (bool): If True, disables the agent.
            start (bool): If True, starts the agent immediately.

        Returns:
            subprocess.CompletedProcess: The result of the `launchctl` command.
        """
        control_type = "start" if start else "disable" if disable else "enable"
        label = self.AGENT_LABEL

        if control_type == "enable":
            label = f"{self.guid}/{label}"

        cmd = [control_type, label]
        return self.execute_launchctl(cmd)

    def execute_launchctl(self, cmd):
        """
        Execute a `launchctl` command.

        Args:
            cmd (list[str]): List of arguments to pass to the `launchctl` binary.

        Returns:
            subprocess.CompletedProcess: The result of the executed command.
        """
        return run_process([self.launchctl_bin, *cmd], start_new_session=True)

    @agent_must_exist
    @safeguard_check()
    def register_agent(self):
        """Register (bootstrap) the LaunchAgent."""
        return self.__boot_agent()

    @agent_must_exist
    @safeguard_check(must_be_booted=True)
    def deregister_agent(self):
        """Deregister (bootout) the LaunchAgent."""
        return self.__boot_agent(bootout=True)

    @agent_must_exist
    @safeguard_check(must_be_booted=True)
    def enable_agent(self):
        """Enable the LaunchAgent."""
        return self.__control_agent()

    @agent_must_exist
    @safeguard_check(must_be_booted=True)
    def disable_agent(self):
        """Disable the LaunchAgent."""
        return self.__control_agent(disable=True)

    @agent_must_exist
    @safeguard_check()
    def start_agent(self):
        """Start the LaunchAgent immediately."""
        if self.is_booted_already:
            return self.__control_agent(start=True)

    def full_install(self):
        """
        Perform a complete setup sequence:
        1. (Re-)Build the agent file
        2. Register the agent
        3. Enable it
        4. Start it immediately
        """
        self.build_agent()
        self.register_agent()
        self.enable_agent()
        self.start_agent()

    @agent_must_exist
    def full_uninstall(self):
        """
        Perform a full uninstallation of the agent.
        This method handles the complete removal of the agent by:
        1. Deregistering the agent from any associated services or configurations.
        2. Deleting the agent and its related resources.
        """

        self.deregister_agent()
        self.delete_agent()

    def check_core(self):
        if not self.launchctl_bin:
            raise EnvironmentError("launchctl binary not found in PATH.")

        if not self.idle_detector_bin:
            raise MissingPackage(
                f"`{self.PACKAGE_NAME}` package is not installed or not found in PATH."
            )

    @cached_property
    def guid(self):
        return f"gui/{getuid()}"

    @property
    def launchctl_bin(self):
        """
        Path: Absolute path to the `launchctl` binary on the system.
        """
        return find_package("launchctl")

    @property
    def is_booted_already(self):
        list_process = self.execute_launchctl(["list"])
        agents = list_process.stdout.split("\t")
        agent_found = next((i for i in agents if i.startswith(self.AGENT_LABEL)), False)
        return bool(agent_found)


def launch_agent(
    *,
    register: bool = False,
    deregister: bool = False,
    enable: bool = False,
    disable: bool = False,
    start_now: bool = False,
    full_install: bool = False,
    full_uninstall: bool = False,
):
    """
    High-level controller for managing a macOS LaunchAgent via AgentInstaller.

    This function serves as the entry point for command-line or programmatic
    control of the LaunchAgent. It validates operation combinations and executes
    the corresponding actions in sequence.

    Args:
        register (bool): Register (bootstrap) the agent.
        deregister (bool): Deregister (bootout) the agent.
        enable (bool): Enable the agent.
        disable (bool): Disable the agent.
        start_now (bool): Start the agent immediately.
        full_install (bool): Perform full setup (register, enable, start).

    Raises:
        ValueError: If conflicting flags are provided (e.g., enable+disable, register+deregister).

    Returns:
        None
    """
    agent_installer = AgentInstaller()

    # Perform full install if explicitly requested or all main flags are set
    if full_install or all((register, enable, start_now)):
        agent_installer.full_install()
    elif full_uninstall or all((deregister, disable)):
        agent_installer.full_uninstall()
    else:
        # Validate flag combinations
        if enable and disable:
            raise ValueError("Cannot enable and disable the agent at the same time.")

        if register and deregister:
            raise ValueError(
                "Cannot register and deregister the agent at the same time."
            )

        # Perform individual operations as requested
        if register:
            agent_installer.register_agent()
        if deregister:
            agent_installer.deregister_agent()
        if enable:
            agent_installer.enable_agent()
        if disable:
            agent_installer.disable_agent()
        if start_now:
            agent_installer.start_agent()
