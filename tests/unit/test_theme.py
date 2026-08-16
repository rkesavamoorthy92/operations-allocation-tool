from __future__ import annotations

import unittest

from operations_allocation.ui.theme import PALETTE, STYLESHEET, apply_theme


class ThemeTestCase(unittest.TestCase):
    def test_stylesheet_is_non_empty(self) -> None:
        self.assertTrue(STYLESHEET.strip())

    def test_palette_colors_are_valid_hex(self) -> None:
        for name, color in PALETTE.items():
            self.assertRegex(color, r"^#[0-9A-Fa-f]{6}$", msg=f"{name} is not a valid hex color")

    def test_stylesheet_references_the_accent_and_danger_properties(self) -> None:
        self.assertIn('QPushButton[accent="true"]', STYLESHEET)
        self.assertIn('QPushButton[danger="true"]', STYLESHEET)

    def test_apply_theme_sets_the_stylesheet_on_the_app(self) -> None:
        calls = []

        class FakeApp:
            def setStyleSheet(self, sheet: str) -> None:
                calls.append(sheet)

        apply_theme(FakeApp())
        self.assertEqual(calls, [STYLESHEET])
