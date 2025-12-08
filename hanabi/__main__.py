"""
Main entry point for running Hanabi as a module.
"""

import sys

def main():
    """Main entry point - supports both CLI and GUI modes."""
    if len(sys.argv) > 1 and sys.argv[1] == "--gui":
        # Launch GUI
        try:
            from .gui.gui_game import play_gui_game
            play_gui_game()
        except ImportError as e:
            if "_tkinter" in str(e) or "tkinter" in str(e).lower():
                print("Error: tkinter is not available in your Python installation.")
                print("\nQuick fix on macOS (use system Python which has tkinter):")
                print("  /usr/bin/python3 -m hanabi --gui")
                print("\nOr install tkinter for Homebrew Python:")
                print("  brew install tcl-tk")
                print("  python3 -m hanabi --gui")
                print("\nAlternatively, use the CLI version:")
                print("  python -m hanabi")
                sys.exit(1)
            else:
                raise
    else:
        # Launch CLI
        from .console.console_game import play_console_game
        play_console_game()

if __name__ == "__main__":
    main()

