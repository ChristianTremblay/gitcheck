# Migration Guide: Python 2 to Python 3 with Rich

This document outlines the changes made to modernize gitcheck for Python 3 and enhance terminal output with the Rich library.

## Major Changes

### 1. Build System Modernization
- **Old**: `setup.py` with manual configuration
- **New**: `pyproject.toml` following PEP 517/518 standards
- All package metadata now in standardized TOML format
- Cleaner, more maintainable configuration

### 2. Python Version Requirements
- **Old**: Python 2.7 and Python 3.3+
- **New**: Python 3.8+ only
- The `from __future__ import` statements have been removed as they're no longer needed

### 2. Dependencies Updated
- **Removed**: `colored`, `colorama`
- **Added**: `rich>=13.0.0`

### 4. Package Configuration
- **Old**: `setup.py` with custom RST processing
- **New**: `pyproject.toml` with standard metadata format
- Installation and build process remain the same for end users
- Follows modern Python packaging standards (PEP 517/518/621)

### 5. Terminal Output Modernization
All terminal output now uses the Rich library for:
- Beautiful, consistent colored output across all platforms (Windows, Linux, macOS)
- Modern markup syntax for colors and styles
- Better readability and user experience
- Automatic color detection and terminal capability handling

### 6. Code Quality Improvements
- Fixed PEP8 compliance issues
- Removed ambiguous variable names (e.g., `l` → `line`)
- Used context managers for file operations
- Modern string formatting with f-strings
- Removed Windows-specific color initialization (Rich handles this automatically)

## Migration Steps for Users

### 1. Upgrade Python
Ensure you have Python 3.8 or later:
```bash
python --version
```

### 2. Install Updated Dependencies
```bash
pip install -r requirements/base.txt
```

Or if installing from source:
```bash
pip install -e .
```

### 3. Update Custom Color Themes (Optional)
If you have a `~/mygitcheck.py` custom configuration file, update the color theme format:

**Old format** (using `colored` library):
```python
from colored import fg, bg, attr

colortheme = {
    'default': attr('reset') + fg('white'),
    'prjchanged': attr('reset') + attr('bold') + fg('deep_pink_1a'),
    # ... etc
}
```

**New format** (using Rich markup):
```python
colortheme = {
    'default': 'white',
    'prjchanged': 'bold deep_pink1',
    'prjremote': 'magenta',
    'prjname': 'chartreuse1',
    'reponame': 'light_goldenrod2',
    'branchname': 'white',
    'fileupdated': 'light_goldenrod2',
    'remoteto': 'deep_sky_blue3',
    'committo': 'violet',
    'commitinfo': 'deep_sky_blue3',
    'commitstate': 'deep_pink1',
}
```

Note: You no longer need to specify `'bell'` and `'reset'` keys - these are handled automatically.

## Benefits of Rich

1. **Cross-platform**: Works perfectly on Windows without special initialization
2. **Modern**: Beautiful terminal output with emoji and advanced formatting support
3. **Consistent**: Same appearance across different terminal emulators
4. **Feature-rich**: Built-in support for tables, panels, progress bars, and more
5. **Maintained**: Actively developed and widely used in the Python ecosystem

## Testing

After migration, test the tool:

```bash
# Simple test
gitcheck

# Verbose output
gitcheck -v

# Help to see all options
gitcheck -h
```

## Rollback

If you need to use the old version temporarily, check out the last Python 2 compatible commit before upgrading.

## Questions?

For issues or questions about the migration, please open an issue on GitHub.
