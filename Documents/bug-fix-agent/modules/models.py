from dataclasses import dataclass


@dataclass
class BugReport:

    exception: str

    package: str

    class_name: str

    method: str

    file: str

    line: int

    source: str

    snippet: str
