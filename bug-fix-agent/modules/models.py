from dataclasses import dataclass
from typing import Optional


@dataclass
class Incident:
    timestamp: str = ""
    device_serial: str = ""
    package: str = ""
    process: str = ""
    pid: Optional[int] = None
    bug_type: str = "UNKNOWN"
    exception: str = ""
    reason: str = ""
    thread: str = ""
    stack_trace: str = ""
    raw_log: str = ""


@dataclass
class BugReport:
    exception: str = ""
    package: str = ""
    class_name: str = ""
    method: str = ""
    file: str = ""
    line: int = 0
    source: str = ""
    snippet: str = ""
