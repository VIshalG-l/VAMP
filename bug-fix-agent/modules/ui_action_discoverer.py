import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class UIAction:
    index: int
    class_name: str
    text: str
    content_desc: str
    resource_id: str
    bounds: str
    clickable: bool
    enabled: bool


class UIActionDiscoverer:
    """
    Generic Android UI action discovery.

    This module does not know:
        - package name
        - activity name
        - button name
        - project path
        - APK name

    It discovers the currently visible UI from Android's
    accessibility/UIAutomator hierarchy.
    """

    def __init__(
        self,
        device_serial: Optional[str] = None,
        dump_path: str = "/sdcard/window_dump.xml",
    ):
        self.device_serial = (
            device_serial or ""
        ).strip()

        self.dump_path = dump_path

    def _adb(self, *args, timeout=15):
        command = ["adb"]

        if self.device_serial:
            command.extend(
                [
                    "-s",
                    self.device_serial,
                ]
            )

        command.extend(args)

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return (
                result.returncode,
                result.stdout or "",
                result.stderr or "",
            )

        except Exception as exc:
            return (
                -1,
                "",
                str(exc),
            )

    def dump_ui(self):
        """
        Dump the current Android UI hierarchy.

        Returns:
            (success, xml_text_or_error)
        """

        code, output, error = self._adb(
            "shell",
            "uiautomator",
            "dump",
            self.dump_path,
            timeout=20,
        )

        if code != 0:
            return False, (
                error
                or output
                or "UIAutomator dump failed."
            )

        # Read the generated XML from the device.
        code, output, error = self._adb(
            "shell",
            "cat",
            self.dump_path,
            timeout=20,
        )

        if code != 0:
            return False, (
                error
                or output
                or "Unable to read UI hierarchy."
            )

        xml_text = output.strip()

        if not xml_text:
            return False, (
                "UI hierarchy is empty."
            )

        return True, xml_text

    @staticmethod
    def _parse_bounds(bounds):
        """
        Extract the center point from Android bounds.

        Example:
            [0,100][500,200]

        Returns:
            (x, y)
        """

        if not bounds:
            return None

        match = re.match(
            r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",
            bounds,
        )

        if not match:
            return None

        x1, y1, x2, y2 = map(
            int,
            match.groups(),
        )

        return (
            (x1 + x2) // 2,
            (y1 + y2) // 2,
        )

    @staticmethod
    def _is_actionable(node):
        """
        Determine whether a UI node can reasonably be
        interacted with.

        We intentionally keep this generic.
        """

        clickable = (
            node.attrib.get(
                "clickable",
                "false",
            ).lower()
            == "true"
        )

        enabled = (
            node.attrib.get(
                "enabled",
                "true",
            ).lower()
            == "true"
        )

        focusable = (
            node.attrib.get(
                "focusable",
                "false",
            ).lower()
            == "true"
        )

        scrollable = (
            node.attrib.get(
                "scrollable",
                "false",
            ).lower()
            == "true"
        )

        text = (
            node.attrib.get(
                "text",
                "",
            )
            or ""
        ).strip()

        content_desc = (
            node.attrib.get(
                "content-desc",
                "",
            )
            or ""
        ).strip()

        return (
            enabled
            and (
                clickable
                or focusable
                or scrollable
                or bool(text)
                or bool(content_desc)
            )
        )

    def parse_actions(self, xml_text):
        """
        Parse UIAutomator XML and return actionable UI nodes.
        """

        if not xml_text:
            return []

        try:
            root = ET.fromstring(
                xml_text
            )
        except ET.ParseError:
            # Some Android versions may prepend text before
            # the XML document. Try to recover from the
            # first <hierarchy> element.
            start = xml_text.find(
                "<hierarchy"
            )

            if start == -1:
                return []

            try:
                root = ET.fromstring(
                    xml_text[start:]
                )
            except ET.ParseError:
                return []

        actions = []
        index = 0

        for node in root.iter("node"):

            if not self._is_actionable(node):
                continue

            class_name = (
                node.attrib.get(
                    "class",
                    "",
                )
                or ""
            )

            text = (
                node.attrib.get(
                    "text",
                    "",
                )
                or ""
            ).strip()

            content_desc = (
                node.attrib.get(
                    "content-desc",
                    "",
                )
                or ""
            ).strip()

            resource_id = (
                node.attrib.get(
                    "resource-id",
                    "",
                )
                or ""
            ).strip()

            bounds = (
                node.attrib.get(
                    "bounds",
                    "",
                )
                or ""
            ).strip()

            clickable = (
                node.attrib.get(
                    "clickable",
                    "false",
                ).lower()
                == "true"
            )

            enabled = (
                node.attrib.get(
                    "enabled",
                    "true",
                ).lower()
                == "true"
            )

            actions.append(
                UIAction(
                    index=index,
                    class_name=class_name,
                    text=text,
                    content_desc=content_desc,
                    resource_id=resource_id,
                    bounds=bounds,
                    clickable=clickable,
                    enabled=enabled,
                )
            )

            index += 1

        return actions

    def discover(self):
        """
        Dump and parse the current UI.

        Returns:
            (success, actions, message)
        """

        print()
        print(
            "[UI] Dumping Android UI hierarchy..."
        )

        success, result = self.dump_ui()

        if not success:
            print(
                "❌ UI dump failed:"
            )
            print(result)

            return (
                False,
                [],
                result,
            )

        actions = self.parse_actions(
            result
        )

        print(
            "✅ UI hierarchy collected."
        )

        print(
            "Discovered actionable elements:",
            len(actions),
        )

        return (
            True,
            actions,
            "UI discovery successful.",
        )

    @staticmethod
    def print_actions(actions):
        print()
        print(
            "========== DISCOVERED UI ACTIONS =========="
        )

        if not actions:
            print(
                "No actionable UI elements found."
            )
            print(
                "=========================================="
            )
            return

        for action in actions:
            print()
            print(
                f"[{action.index}]"
            )

            print(
                "  Class       :",
                action.class_name
                or "Unknown",
            )

            print(
                "  Text        :",
                action.text
                or "None",
            )

            print(
                "  Description :",
                action.content_desc
                or "None",
            )

            print(
                "  Resource ID :",
                action.resource_id
                or "None",
            )

            print(
                "  Bounds      :",
                action.bounds
                or "Unknown",
            )

            print(
                "  Clickable   :",
                action.clickable,
            )

            print(
                "  Enabled     :",
                action.enabled,
            )

        print(
            "=========================================="
        )

    def click_action(self, action):
        """
        Click the center of a discovered UI element.

        This method intentionally accepts a discovered
        UIAction rather than a hard-coded button name.
        """

        if action is None:
            return False, (
                "No UI action supplied."
            )

        center = self._parse_bounds(
            action.bounds
        )

        if center is None:
            return False, (
                "Unable to determine "
                "UI element coordinates."
            )

        x, y = center

        print()
        print(
            "[UI] Performing action:"
        )

        print(
            "  Class:",
            action.class_name
            or "Unknown",
        )

        print(
            "  Text:",
            action.text
            or "None",
        )

        print(
            "  Description:",
            action.content_desc
            or "None",
        )

        print(
            "  Coordinates:",
            f"({x}, {y})",
        )

        code, output, error = self._adb(
            "shell",
            "input",
            "tap",
            str(x),
            str(y),
            timeout=15,
        )

        if code != 0:
            return False, (
                error
                or output
                or "UI action failed."
            )

        time.sleep(1)

        return True, (
            f"Tapped UI element at ({x}, {y})."
        )


if __name__ == "__main__":

    print()
    print("=" * 70)
    print("             GENERIC UI ACTION DISCOVERY")
    print("=" * 70)

    discoverer = UIActionDiscoverer()

    success, actions, message = (
        discoverer.discover()
    )

    if not success:
        print()
        print(
            "❌ UI discovery failed."
        )
        raise SystemExit(1)

    discoverer.print_actions(
        actions
    )

    print()
    print(
        "Discovery Status : SUCCESS"
    )
