"""
Helper utilities for GUI testing.
Provides test-friendly versions of GUI components.
"""

import tkinter as tk
from typing import Optional
from .gui_display import GUIDisplay
from .gui_game import GUIGame


class TestFriendlyGUIDisplay(GUIDisplay):
    """GUIDisplay with messageboxes disabled for testing."""

    def __init__(self, root: tk.Tk):
        """Initialize test-friendly display."""
        super().__init__(root)
        self.set_suppress_dialogs(True)


class TestFriendlyGUIGame(GUIGame):
    """GUIGame with dialogs disabled for testing."""

    def __init__(self, root: tk.Tk):
        """Initialize test-friendly game."""
        super().__init__(root)
        self._suppress_dialogs = True
        if self._display:
            self._display.set_suppress_dialogs(True)

