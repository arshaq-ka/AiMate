import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from character.character_window import CharacterWindow
from character.states import CharacterState


class CharacterWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = CharacterWindow()
        self.window.animation.pause()

    def tearDown(self) -> None:
        self.window.stop_animation()
        self.window.deleteLater()
        self.app.processEvents()

    def test_animation_pause_and_resume_update_state(self) -> None:
        self.assertEqual(self.window.state, CharacterState.PAUSED)
        self.window.resume_animation()
        self.assertEqual(self.window.state, CharacterState.IDLE)
        self.window.pause_animation()
        self.assertEqual(self.window.state, CharacterState.PAUSED)

    def test_close_hides_instead_of_destroying_window(self) -> None:
        self.window.show()
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertIsNotNone(self.window.animation)

    def test_character_can_render_without_a_native_window(self) -> None:
        image = self.window.grab().toImage()
        self.assertFalse(image.isNull())
        self.assertEqual(image.width(), self.window.width())
        self.assertEqual(image.height(), self.window.height())


if __name__ == "__main__":
    unittest.main()
