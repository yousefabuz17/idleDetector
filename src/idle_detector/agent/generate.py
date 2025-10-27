import plistlib
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from ..models.machine import MacOS
from ..utils.common import PROJECT, decode_string, type_name
from ..utils.os_modules import find_package, get_sys_path, rm_file


@dataclass(init=False)
class AgentGenerator:
    PACKAGE_NAME: ClassVar[str] = "idle-detector"
    AGENT_LABEL: ClassVar[str] = f"com.github.{PROJECT}"
    AGENT_PATH: ClassVar[Path] = (
        Path("~/Library/LaunchAgents/") / AGENT_LABEL
    ).expanduser()
    agent_file: ClassVar[Path] = AGENT_PATH.with_name(AGENT_PATH.name + ".plist")

    def __str__(self):
        return "{}(agent_file={!r})".format(type_name(self), self.agent_file)

    def agent_file_exists(self):
        return self.agent_file.exists()

    def generate_data(self):
        log_paths = MacOS.log_files()
        return {
            "Label": self.AGENT_LABEL,
            "ProgramArguments": [self.idle_detector_bin],
            "EnvironmentVariables": {"PATH": get_sys_path()},
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": log_paths.out_log.as_posix(),
            "StandardErrorPath": log_paths.err_log.as_posix(),
        }

    def read_agent(self, xml_format: bool = True):
        if not self.agent_file_exists():
            return

        with self.agent_file.open("rb") as af:
            if xml_format:
                af_xml = plistlib.dumps(
                    self.generate_data(), fmt=plistlib.FMT_XML, sort_keys=False
                )
                return decode_string(af_xml)
            return plistlib.load(af, fmt=plistlib.FMT_XML)

    def build_agent(self):
        with self.agent_file.open("wb") as af:
            plistlib.dump(
                self.generate_data(),
                af,
                fmt=plistlib.FMT_XML,
                sort_keys=False,
            )

    def delete_agent(self):
        rm_file(self.agent_file)

    @property
    def idle_detector_bin(self):
        return find_package(self.PACKAGE_NAME, default="")
