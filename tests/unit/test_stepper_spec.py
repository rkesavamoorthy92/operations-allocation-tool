from __future__ import annotations

import re
import unittest

from operations_allocation.ui.stepper_spec import STEPPER_ACTIONS, STEPPER_GROUPS


def _has_unescaped_ampersand(text: str) -> bool:
    """A lone '&' is a Qt keyboard-mnemonic marker (renders as an
    underline on the next letter, or "eats" it entirely in a QGroupBox
    title) -- '&&' is required to display a literal ampersand.
    """
    return re.search(r"(?<!&)&(?!&)", text) is not None


class StepperGroupsTestCase(unittest.TestCase):
    def test_every_action_key_appears_in_exactly_one_group(self) -> None:
        all_action_keys = [key for key, _label, _states in STEPPER_ACTIONS]
        grouped_keys = [key for _label, keys in STEPPER_GROUPS for key in keys]
        self.assertEqual(sorted(grouped_keys), sorted(all_action_keys), "A stepper action is missing from (or duplicated across) STEPPER_GROUPS.")
        self.assertEqual(len(grouped_keys), len(set(grouped_keys)), "An action key appears in more than one group.")

    def test_group_labels_are_unique(self) -> None:
        labels = [label for label, _keys in STEPPER_GROUPS]
        self.assertEqual(len(labels), len(set(labels)))

    def test_no_label_has_an_unescaped_ampersand(self) -> None:
        for _key, label, _states in STEPPER_ACTIONS:
            self.assertFalse(_has_unescaped_ampersand(label), f"Action label {label!r} has an unescaped '&' -- use '&&' to display it literally.")
        for group_label, _keys in STEPPER_GROUPS:
            self.assertFalse(_has_unescaped_ampersand(group_label), f"Group label {group_label!r} has an unescaped '&' -- use '&&' to display it literally.")
