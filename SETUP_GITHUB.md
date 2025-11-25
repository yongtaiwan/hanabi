# GitHub Setup Guide for Hanabi Project

## Step 1: Configure Git (if not already done)

```bash
# Set your name and email (if not already configured globally)
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# Verify configuration
git config --list
```

## Step 2: Create GitHub Repository

### Option A: Using GitHub Web Interface (Recommended)

1. Go to [GitHub.com](https://github.com) and sign in
2. Click the **"+"** icon in the top right → **"New repository"**
3. Repository settings:
   - **Name**: `hanabi` (or `hanabi-game`)
   - **Description**: "Python implementation of the Hanabi card game with AI support"
   - **Visibility**: Public or Private (your choice)
   - **DO NOT** initialize with README, .gitignore, or license (we already have these)
4. Click **"Create repository"**
5. Copy the repository URL (e.g., `https://github.com/yourusername/hanabi.git`)

### Option B: Using GitHub CLI (if installed)

```bash
gh repo create hanabi --public --source=. --remote=origin --push
```

## Step 3: Connect Local Repository to GitHub

After creating the repository on GitHub, run these commands:

```bash
# Add remote (replace with your actual GitHub URL)
git remote add origin https://github.com/YOUR_USERNAME/hanabi.git

# Verify remote
git remote -v

# Stage all files
git add .

# Create initial commit
git commit -m "Initial commit: Hanabi game implementation with console UI"

# Push to GitHub (main branch)
git branch -M main
git push -u origin main
```

## Step 4: Verify Setup

1. Go to your GitHub repository page
2. You should see all your files
3. Check that `.gitignore` is working (no `__pycache__` folders visible)

---

## Recommended Cursor/VS Code Extensions

### Essential Extensions

1. **Python** (by Microsoft)
   - Python language support, IntelliSense, debugging
   - Extension ID: `ms-python.python`

2. **Pylance** (by Microsoft)
   - Fast, feature-rich language server for Python
   - Extension ID: `ms-python.vscode-pylance`

3. **GitLens** (by GitKraken)
   - Enhanced Git capabilities, blame annotations, file history
   - Extension ID: `eamodio.gitlens`

4. **Python Docstring Generator** (by Nils Werner)
   - Auto-generate docstrings
   - Extension ID: `nils-werner.python-docstring-generator`

### Recommended Extensions

5. **Markdown All in One** (by Yu Zhang)
   - Markdown preview, table of contents, auto-completion
   - Extension ID: `yzhang.markdown-all-in-one`

6. **Python Test Explorer** (by Little Fox Team)
   - Test discovery and running
   - Extension ID: `littlefoxteam.vscode-python-test-adapter`

7. **YAML** (by Red Hat)
   - YAML language support (for game history files)
   - Extension ID: `redhat.vscode-yaml`

8. **Error Lens** (by Alexander)
   - Inline error highlighting
   - Extension ID: `usernamehw.errorlens`

9. **Code Spell Checker** (by Street Side Software)
   - Spell checking for code and comments
   - Extension ID: `streetsidesoftware.code-spell-checker`

10. **Ruff** (by Astral Software)
    - Fast Python linter and formatter
    - Extension ID: `charliermarsh.ruff`

### Optional but Useful

11. **Git Graph** (by mhutchie)
    - Visualize git history
    - Extension ID: `mhutchie.git-graph`

12. **Todo Tree** (by Gruntfuggly)
    - Highlight TODO comments
    - Extension ID: `gruntfuggly.todo-tree`

13. **Better Comments** (by Aaron Bond)
    - Colorize comments
    - Extension ID: `aaron-bond.better-comments`

---

## Installing Extensions in Cursor

### Method 1: Command Palette
1. Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
2. Type "Extensions: Install Extensions"
3. Search for extension name or ID
4. Click "Install"

### Method 2: Extensions View
1. Click the Extensions icon in the sidebar (or `Cmd+Shift+X` / `Ctrl+Shift+X`)
2. Search for extensions
3. Click "Install"

### Method 3: Quick Install (Recommended)
Run this command to install all recommended extensions at once:

```bash
# Create a script to install extensions
cat > install_extensions.sh << 'EOF'
#!/bin/bash
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension eamodio.gitlens
code --install-extension nils-werner.python-docstring-generator
code --install-extension yzhang.markdown-all-in-one
code --install-extension littlefoxteam.vscode-python-test-adapter
code --install-extension redhat.vscode-yaml
code --install-extension usernamehw.errorlens
code --install-extension streetsidesoftware.code-spell-checker
code --install-extension charliermarsh.ruff
EOF

chmod +x install_extensions.sh
./install_extensions.sh
```

---

## Recommended Cursor Settings

Create or update `.vscode/settings.json`:

```json
{
  // Python settings
  "python.defaultInterpreterPath": "python3",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "none",
  "python.formatting.ruffEnabled": true,
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  },

  // Git settings
  "git.enableSmartCommit": true,
  "git.confirmSync": false,
  "git.autofetch": true,

  // Editor settings
  "editor.rulers": [80, 100],
  "editor.tabSize": 4,
  "editor.insertSpaces": true,
  "files.trimTrailingWhitespace": true,
  "files.insertFinalNewline": true,
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true
  },

  // Markdown settings
  "markdown.preview.breaks": true,
  "markdown.preview.fontSize": 14,

  // File associations
  "files.associations": {
    "*.yaml": "yaml",
    "*.yml": "yaml"
  }
}
```

---

## Git Workflow Best Practices

### Branch Strategy

```bash
# Main branch for stable code
git checkout main

# Create feature branch
git checkout -b feature/ai-interface

# Make changes, commit
git add .
git commit -m "Add AI player interface"

# Push feature branch
git push -u origin feature/ai-interface

# Create Pull Request on GitHub, then merge to main
```

### Commit Message Guidelines

Use clear, descriptive commit messages:

```bash
# Good examples:
git commit -m "Add RuleSet interface for game variants"
git commit -m "Fix hint alignment bug when cards are drawn"
git commit -m "Refactor ConsoleDisplay to implement Display interface"

# Bad examples:
git commit -m "fix"
git commit -m "updates"
git commit -m "WIP"
```

### Useful Git Aliases

Add these to your `~/.gitconfig`:

```bash
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.cm commit
git config --global alias.unstage 'reset HEAD --'
git config --global alias.last 'log -1 HEAD'
git config --global alias.visual '!gitk'
```

---

## Next Steps

1. ✅ Install recommended extensions
2. ✅ Configure settings
3. ✅ Create GitHub repository
4. ✅ Push initial code
5. 🔄 Set up GitHub Actions for CI/CD (optional)
6. 🔄 Add project badges to README (optional)
7. 🔄 Set up issue templates (optional)

---

## Troubleshooting

### Issue: "Permission denied (publickey)"
**Solution**: Set up SSH keys or use HTTPS with personal access token

### Issue: "Repository not found"
**Solution**: Check that you've created the repository on GitHub first

### Issue: Extensions not installing
**Solution**: Make sure you're using `code` command (VS Code) or check Cursor's extension marketplace

### Issue: Python interpreter not found
**Solution**: Install Python 3.8+ and configure path in settings

