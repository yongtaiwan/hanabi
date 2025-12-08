# Installing tkinter for Hanabi GUI

The GUI version of Hanabi requires tkinter, which is not always included with Python installations (especially Homebrew Python on macOS).

## macOS Solutions

### Option 1: Install tkinter for Homebrew Python (Recommended)
If you're using Homebrew Python (most common), install tkinter support:

```bash
# Install tcl-tk (required for tkinter)
brew install tcl-tk

# Test if tkinter works (it should work if tcl-tk is installed)
python3 -c "import tkinter; print('tkinter works!')"

# If tkinter doesn't work, reinstall Python to link with tcl-tk
brew reinstall python@3.14

# Run GUI
python3 -m hanabi --gui
```

**Note**: If tkinter already works (you see "tkinter works!"), you can skip the reinstall step and just run the GUI.

### Option 2: Use System Python (if available)
If system Python is available and has tkinter:
```bash
/usr/bin/python3 -m hanabi --gui
```

Note: System Python may require newer macOS versions. If you get version errors, use Option 1 instead.

### Option 3: Use pyenv Python with tkinter
If using pyenv:
```bash
# Install tcl-tk first
brew install tcl-tk

# Install Python with tkinter support
env PYTHON_CONFIGURE_OPTS="--with-tcltk-includes='-I$(brew --prefix tcl-tk)/include' --with-tcltk-libs='-L$(brew --prefix tcl-tk)/lib -ltcl8.6 -ltk8.6'" pyenv install 3.14.0
```

### Option 3: Use pyenv Python with tkinter
If using pyenv:
```bash
# Install tcl-tk first
brew install tcl-tk

# Install Python with tkinter support
env PYTHON_CONFIGURE_OPTS="--with-tcltk-includes='-I$(brew --prefix tcl-tk)/include' --with-tcltk-libs='-L$(brew --prefix tcl-tk)/lib -ltcl8.6 -ltk8.6'" pyenv install 3.14.0
```

## Linux Solutions

Most Linux distributions include tkinter with Python:
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk

# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

## Windows

tkinter is usually included with standard Python installations on Windows. If not, reinstall Python from python.org and ensure "tcl/tk" is selected during installation.

## Verify Installation

Test if tkinter is available:
```python
python3 -c "import tkinter; print('tkinter is available!')"
```

If this works, you can run the GUI:
```bash
python -m hanabi --gui
```

## Alternative: Use CLI Version

If you can't install tkinter, you can always use the CLI version:
```bash
python -m hanabi
```

