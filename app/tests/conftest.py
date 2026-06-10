"""
Pytest configuration for the test suite.

Adds the project root to sys.path so tests in the unit/ integration/ security/
subfolders can `import app...` without per-file path hacks.
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
