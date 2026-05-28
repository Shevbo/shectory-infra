import sys
import os

# Ensure project root is on sys.path so that `sources.*` imports work
# regardless of how pytest discovers and imports test files.
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)
