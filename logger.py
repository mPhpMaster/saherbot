import logging
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_LOG_DIR = _ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / (time.strftime("%d-%m-%Y") + ".log")

_configured = False


def release_dashboard_file_handlers() -> None:
    """Close ``FileHandler``s writing under ``logs/`` so daily logs can be deleted or truncated (Windows locks)."""
    global _configured, _LOG_FILE
    try:
        logs_dir = _LOG_DIR.resolve()
    except OSError:
        return
    root = logging.getLogger()
    for h in list(root.handlers):
        if not isinstance(h, logging.FileHandler):
            continue
        try:
            bf = getattr(h, "baseFilename", None)
            if not bf:
                continue
            p = Path(str(bf)).resolve()
            p.relative_to(logs_dir)
        except (ValueError, AttributeError, OSError, TypeError):
            continue
        try:
            h.flush()
            h.close()
        except Exception:
            pass
        try:
            root.removeHandler(h)
        except ValueError:
            pass
    _configured = False
    _LOG_FILE = _LOG_DIR / (time.strftime("%d-%m-%Y") + ".log")


def _ensure_logging() -> None:
    global _configured, _LOG_FILE
    if _configured:
        return
    _LOG_FILE = _LOG_DIR / (time.strftime("%d-%m-%Y") + ".log")
    fmt = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    fh = logging.FileHandler(str(_LOG_FILE), encoding="utf-8", mode="a")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    _configured = True


def log(message: str, type: str = "info") -> None:
    _ensure_logging()
    _time = time.strftime("%d-%m-%Y %H:%M:%S")
    line = f"{_time} [{type}]: {message}"
    try:
        print(line, file=sys.stderr, flush=True)
    except Exception:
        pass
    lg = logging.getLogger()
    if type == "error":
        lg.error(message)
    elif type == "info":
        lg.info(message)
    else:
        lg.debug(message)
    for h in lg.handlers:
        try:
            h.flush()
        except Exception:
            pass
