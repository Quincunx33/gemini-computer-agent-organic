import os
import unittest
from unittest.mock import patch

import platform_support
from planner import tools_for_task
from tools.control import open_app
from tools.gui_control import screenshot
from tools.terminal import run_command


class PlatformSupportTests(unittest.TestCase):
    def _detect(self, system, **env):
        clean = {key: value for key, value in env.items() if value is not None}
        with patch("platform_support.platform.system", return_value=system), patch("platform_support.platform.release", return_value="test-release"), patch("platform_support.platform.machine", return_value="test-machine"), patch.dict(os.environ, clean, clear=True):
            return platform_support.detect()

    def test_termux_is_detected_before_linux_gui_logic(self):
        info = self._detect("Linux", TERMUX_VERSION="0.118", DISPLAY=":1")
        self.assertEqual(info.profile, "termux")
        self.assertNotIn("screenshot", platform_support.supported_tool_names(info))
        self.assertIn("gui_capabilities", platform_support.supported_tool_names(info))

    def test_ios_shell_never_gets_desktop_tools(self):
        info = self._detect("Darwin", A_SHELL="1", DISPLAY=":1")
        self.assertEqual(info.profile, "ios_shell")
        supported = platform_support.supported_tool_names(info)
        self.assertNotIn("open_app", supported)
        self.assertNotIn("list_processes", supported)
        self.assertNotIn("mouse_click", supported)
        self.assertIn("read_file", supported)

    def test_windows_has_windows_shell_profile(self):
        info = self._detect("Windows", SystemRoot="C:\\Windows")
        self.assertEqual(info.profile, "windows")
        self.assertEqual(info.shell_family, "windows-shell")
        self.assertIn("open_app", platform_support.supported_tool_names(info))

    def test_task_schema_is_filtered_by_platform(self):
        ios = self._detect("Darwin", IOS_SHELL="1")
        tools = tools_for_task("take a screenshot and click", platform_info=ios)
        names = {tool["name"] for tool in tools}
        self.assertIn("gui_capabilities", names)
        self.assertNotIn("screenshot", names)
        self.assertNotIn("mouse_click", names)

    def test_direct_incompatible_tools_fail_safely(self):
        with patch("tools.control.detect", return_value=self._detect("Darwin", IOS_SHELL="1")):
            result = open_app("https://example.com")
        self.assertEqual(result["code"], "UNSUPPORTED_PLATFORM")
        with patch("tools.gui_control.detect", return_value=self._detect("Darwin", IOS_SHELL="1")):
            result = screenshot("screen.png")
        self.assertEqual(result["ok"], False)

    def test_incompatible_shell_syntax_is_rejected(self):
        windows = self._detect("Windows", SystemRoot="C:\\Windows")
        with patch("tools.terminal.detect", return_value=windows):
            result = run_command("ls -la", approved=True)
        self.assertEqual(result["error"]["code"], "UNSUPPORTED_PLATFORM")

        linux = self._detect("Linux")
        with patch("tools.terminal.detect", return_value=linux):
            result = run_command("powershell Get-ChildItem", approved=True)
        self.assertEqual(result["error"]["code"], "UNSUPPORTED_PLATFORM")


if __name__ == "__main__":
    unittest.main()
