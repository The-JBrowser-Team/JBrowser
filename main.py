"""JBrowser entry point (used by `python main.py` and the PyInstaller build)."""
import sys

from jbrowser.app import run

if __name__ == "__main__":
    sys.exit(run(sys.argv))
