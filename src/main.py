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

# Global PyTorch 2.6+ backward compatibility patch for third-party checkpoints (pyannote/lightning/speechbrain)
try:
    import torch
    _real_torch_load = getattr(torch, "_easper_orig_load", None)
    if _real_torch_load is None:
        _real_torch_load = torch.load
        torch._easper_orig_load = _real_torch_load

    def _safe_torch_load(*args, **kwargs):
        kwargs["weights_only"] = False
        try:
            return _real_torch_load(*args, **kwargs)
        except TypeError:
            kwargs.pop("weights_only", None)
            return _real_torch_load(*args, **kwargs)
    torch.load = _safe_torch_load

    if hasattr(torch.serialization, "add_safe_globals"):
        try:
            import torch.torch_version
            torch.serialization.add_safe_globals([torch.torch_version.TorchVersion])
        except Exception:
            pass
        try:
            import pyannote.audio.core.task
            torch.serialization.add_safe_globals([pyannote.audio.core.task.Specifications])
        except Exception:
            pass
except Exception:
    pass


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
