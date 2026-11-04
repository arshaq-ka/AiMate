import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from character.character_window import CharacterWindow
from character.tray import SystemTrayController


class TrayQuitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.character = CharacterWindow()
        self.character.animation.pause()
        self.tray = SystemTrayController(
            self.app,
            self.character,
            lambda: None,
        )
        self.exit_mock = Mock()
        self.app.exit = self.exit_mock
        self.quit_requests = []
        self.tray.quit_requested.connect(
            lambda: self.quit_requests.append(True)
        )

    def tearDown(self) -> None:
        self.tray._icon.hide()
        self.character.stop_animation()
        self.character.deleteLater()
        self.tray.deleteLater()
        self.app.processEvents()

    def test_tray_quit_hides_icon_and_requests_application_exit(self) -> None:
        self.character.show()
        self.tray.show()

        self.tray._quit_action.trigger()

        self.assertFalse(self.tray._icon.isVisible())
        self.assertFalse(self.character.isVisible())
        self.assertEqual(self.quit_requests, [True])
        self.exit_mock.assert_called_once_with(0)

    def test_character_quit_signal_is_connected_to_tray_quit_action(self) -> None:
        self.character.quit_requested.connect(self.tray.quit_application)

        self.character.quit_requested.emit()

        self.assertEqual(self.quit_requests, [True])
        self.exit_mock.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
