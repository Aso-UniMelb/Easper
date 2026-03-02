"""
Entry point for Easper application.
Detects mode: if run with arguments → CLI, otherwise → UI.
"""
import sys
import os

# Add the project root to Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def main():
    # Check if CLI arguments provided (excluding just the script name)
    if len(sys.argv) > 1:
        # CLI mode
        from src.cli import main as cli_main
        return cli_main()
    else:
        # UI mode
        from src.ui.launcher import main as ui_main
        return ui_main()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main() or 0)
