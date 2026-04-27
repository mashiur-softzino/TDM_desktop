"""
Logging setup for TDM Report — Therapeutic Drug Monitoring Software

One set of log files per calendar day inside the logs/ folder:
  logs/app_YYYY-MM-DD.log   — general application events (INFO+)
  logs/error_YYYY-MM-DD.log — errors with full tracebacks (ERROR+)
  logs/audit_YYYY-MM-DD.log — patient data access trail

Old files are never deleted automatically — keep or archive as needed
for compliance/audit purposes.
"""

import logging
import sys
import traceback
from datetime import date
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_FMT_APP   = "%(asctime)s | %(levelname)-8s | %(message)s"
_FMT_ERROR = "%(asctime)s | %(levelname)-8s | %(pathname)s:%(lineno)d | %(message)s"
_FMT_AUDIT = "%(asctime)s | AUDIT | %(message)s"
_DATE_FMT  = "%Y-%m-%d %H:%M:%S"


class _DailyFileHandler(logging.FileHandler):
    """Opens a new dated log file each calendar day automatically."""

    def __init__(self, prefix: str, level: int, fmt: str):
        self._prefix = prefix
        self._log_date = date.today()
        path = self._dated_path()
        super().__init__(path, encoding="utf-8", delay=False)
        self.setLevel(level)
        self.setFormatter(logging.Formatter(fmt, datefmt=_DATE_FMT))

    def _dated_path(self) -> Path:
        return LOG_DIR / f"{self._prefix}_{self._log_date.isoformat()}.log"

    def emit(self, record: logging.LogRecord):
        today = date.today()
        if today != self._log_date:
            self._log_date = today
            self.close()
            self.baseFilename = str(self._dated_path())
            self.stream = self._open()
        super().emit(record)


# ── Loggers ───────────────────────────────────────────────────────

app_log   = logging.getLogger("tdm.app")
error_log = logging.getLogger("tdm.error")
audit_log = logging.getLogger("tdm.audit")

app_log.setLevel(logging.DEBUG)
error_log.setLevel(logging.ERROR)
audit_log.setLevel(logging.DEBUG)

app_log.addHandler(_DailyFileHandler("app",   logging.INFO,  _FMT_APP))
error_log.addHandler(_DailyFileHandler("error", logging.ERROR, _FMT_ERROR))
audit_log.addHandler(_DailyFileHandler("audit", logging.DEBUG, _FMT_AUDIT))

for _lg in (app_log, error_log, audit_log):
    _lg.propagate = False


# ── Convenience functions ─────────────────────────────────────────

def log_startup():
    app_log.info(f"Application started | Python {sys.version.split()[0]}")

def log_shutdown():
    app_log.info("Application closed")

def log_license_activated(license_key: str, expires_at: str):
    app_log.info(f"License activated | key={license_key[:12]}... | expires={expires_at}")
    audit_log.info(f"LICENSE_ACTIVATED | key={license_key[:12]}... | expires={expires_at}")

def log_license_expired():
    app_log.warning("License expired — application closing")
    audit_log.info("LICENSE_EXPIRED | application forced closed")

def log_report_generated(pid: str, name: str, drug: str, auc: float | None):
    app_log.info(f"Report generated | pid={pid} | patient={name} | drug={drug} | auc={auc}")
    audit_log.info(f"REPORT_GENERATED | pid={pid} | patient={name} | drug={drug} | auc={auc}")

def log_draft_saved(pid: str, name: str):
    app_log.info(f"Draft saved | pid={pid} | patient={name}")
    audit_log.info(f"DRAFT_SAVED | pid={pid} | patient={name}")

def log_record_loaded(record_id: str, pid: str, name: str, source: str):
    app_log.info(f"Record loaded | id={record_id} | pid={pid} | patient={name} | source={source}")
    audit_log.info(f"RECORD_LOADED | id={record_id} | pid={pid} | patient={name} | source={source}")

def log_record_deleted(record_id: str, pid: str, name: str):
    app_log.warning(f"Record deleted | id={record_id} | pid={pid} | patient={name}")
    audit_log.info(f"RECORD_DELETED | id={record_id} | pid={pid} | patient={name}")

def log_report_printed(pid: str, name: str):
    app_log.info(f"Report printed/exported | pid={pid} | patient={name}")
    audit_log.info(f"REPORT_PRINTED | pid={pid} | patient={name}")

def log_db_error(operation: str, exc: Exception):
    error_log.error(f"Database error | op={operation} | {exc}", exc_info=True)
    app_log.error(f"Database error during '{operation}': {exc}")

def log_error(context: str, exc: Exception):
    error_log.error(f"{context} | {exc}", exc_info=True)
    app_log.error(f"Error in {context}: {exc}")


# ── Global unhandled exception hook ──────────────────────────────
def _handle_unhandled(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    error_log.critical(f"UNHANDLED EXCEPTION\n{tb_str}")
    app_log.critical(f"Unhandled exception: {exc_value}")

sys.excepthook = _handle_unhandled
