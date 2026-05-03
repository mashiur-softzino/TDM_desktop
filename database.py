"""
TDM Report — Database layer
SQLite backend replacing saved_patients.json
"""

import json
import random
import shutil
import sqlite3
import string
from pathlib import Path
from datetime import datetime

import sqlcipher3
from app_paths import backups_dir, db_file, migrate_legacy_file

DB_FILE = db_file()
migrate_legacy_file("tdm_report.db", DB_FILE)
SQLITE_HEADER = b"SQLite format 3\x00"
BACKUP_KEEP_COUNT = 5
DEFAULT_MEDICATIONS_SEED = [
    "Tacrolimus (TAC)", "Cyclosporine (CsA)", "Mycophenolate (MPA)",
    "Prednisolone", "Methylprednisolone", "Amlodipine", "Metoprolol",
    "Losartan", "Atorvastatin", "Rosuvastatin", "Furosemide",
    "Spironolactone", "Omeprazole", "Pantoprazole", "Insulin",
    "Glimepiride", "Metformin", "Febuxostat", "Allopurinol",
    "Cotrimoxazole", "Valganciclovir", "Fluconazole", "Omega-3",
    "Calcium + Vitamin D", "Sirolimus", "Everolimus", "Azathioprine",
    "Linagliptin", "Ostoref-D", "Shelcal",
]


def _build_sqlcipher_password() -> str:
    """Rebuild the SQLCipher key at runtime so it is not stored as plain text."""
    mask = 0x37
    parts = [
        99, 115, 122, 104, 101, 114, 103, 120, 101, 99, 104,
        100, 120, 113, 99, 109, 126, 121, 120, 104, 5, 7,
        5, 1, 104, 115, 117, 104, 124, 114, 110,
    ]
    return "".join(chr(value ^ mask) for value in parts)


SQLCIPHER_PASSWORD = _build_sqlcipher_password()


# ─────────────────────────────────────────
# Connection
# ─────────────────────────────────────────

def _is_plain_sqlite(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("rb") as fh:
        return fh.read(len(SQLITE_HEADER)) == SQLITE_HEADER


def _set_cipher_key(conn, password: str):
    escaped = password.replace("'", "''")
    conn.execute(f"PRAGMA key = '{escaped}'")


def _encrypted_connection(path: Path) -> sqlcipher3.Connection:
    conn = sqlcipher3.connect(str(path))
    _set_cipher_key(conn, SQLCIPHER_PASSWORD)
    return conn


def _backup_files() -> list[Path]:
    return sorted(
        backups_dir().glob("tdm_report.backup.*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _validate_database(path: Path) -> bool:
    if not path.exists():
        return False

    conn = _encrypted_connection(path)
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        result = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(result and result[0] == "ok")
    except Exception:
        return False
    finally:
        conn.close()


def _remove_sidecar_files(path: Path):
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except Exception:
                pass


def _prune_database_backups():
    for old_backup in _backup_files()[BACKUP_KEEP_COUNT:]:
        try:
            old_backup.unlink()
        except Exception:
            pass


def create_database_backup(reason: str = "manual") -> Path | None:
    """Create a consistent encrypted database backup and keep the newest 5."""
    if not DB_FILE.exists():
        restore_latest_database_backup()
    if not DB_FILE.exists():
        return None

    safe_reason = "".join(ch for ch in reason.lower() if ch.isalnum() or ch in ("-", "_")) or "manual"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backups_dir() / f"tdm_report.backup.{timestamp}.{safe_reason}.db"

    source = _encrypted_connection(DB_FILE)
    try:
        source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        result = source.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError("Source database integrity check failed")
    finally:
        source.close()

    shutil.copy2(DB_FILE, backup_path)
    if not _validate_database(backup_path):
        if backup_path.exists():
            backup_path.unlink()
        raise RuntimeError("Database backup integrity check failed")
    _remove_sidecar_files(backup_path)

    _prune_database_backups()
    return backup_path


def restore_latest_database_backup() -> Path | None:
    """Restore the newest valid backup when the main database is missing/corrupt."""
    for backup_path in _backup_files():
        if not _validate_database(backup_path):
            continue
        _remove_sidecar_files(backup_path)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if DB_FILE.exists():
            corrupt_path = backups_dir() / f"tdm_report.corrupt-{timestamp}.db"
            try:
                shutil.copy2(DB_FILE, corrupt_path)
            except Exception:
                pass

        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, DB_FILE)
        _remove_sidecar_files(DB_FILE)
        return backup_path

    return None


def _encrypt_plain_database():
    if not _is_plain_sqlite(DB_FILE):
        return

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backups_dir() / f"tdm_report.plain.bak-{timestamp}.db"
    encrypted_path = DB_FILE.with_suffix(f".encrypted-{timestamp}.db")

    source = sqlite3.connect(str(DB_FILE))
    target = sqlcipher3.connect(str(encrypted_path))
    try:
        _set_cipher_key(target, SQLCIPHER_PASSWORD)
        target.executescript("\n".join(source.iterdump()))
        ok = target.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise RuntimeError(f"Encrypted database integrity check failed: {ok}")
        target.commit()
    finally:
        source.close()
        target.close()

    shutil.copy2(DB_FILE, backup_path)
    encrypted_path.replace(DB_FILE)


def _connect() -> sqlcipher3.Connection:
    if not DB_FILE.exists():
        restore_latest_database_backup()

    _encrypt_plain_database()
    conn = _encrypted_connection(DB_FILE)
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except Exception:
        conn.close()
        if restore_latest_database_backup():
            conn = _encrypted_connection(DB_FILE)
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        else:
            raise
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA secure_delete = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.row_factory = sqlcipher3.Row
    return conn


# ─────────────────────────────────────────
# Schema
# ─────────────────────────────────────────

def _column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r['name'] == column for r in rows)


def init_db():
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.executescript("""
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS patients (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                pid            TEXT UNIQUE,
                invoice_number TEXT UNIQUE,
                name           TEXT,
                age            TEXT,
                sex            TEXT,
                invoice_date   TEXT,
                report_number  TEXT,
                dept           TEXT,
                diagnosis      TEXT,
                tx_date        TEXT,
                delivery_date TEXT
            );

            CREATE TABLE IF NOT EXISTS doctors (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                designation    TEXT,
                signature_path TEXT,
                type           TEXT NOT NULL DEFAULT 'doctor'
            );

            CREATE TABLE IF NOT EXISTS records (
                id                     TEXT PRIMARY KEY,
                patient_id             INTEGER REFERENCES patients(id),
                record_type            TEXT NOT NULL DEFAULT 'sample',
                saved_at               TEXT NOT NULL,
                report_path            TEXT,
                sample_rows_json       TEXT,
                duration_options_json  TEXT,
                drug                   TEXT,
                preparation            TEXT,
                dose                   TEXT,
                dose_dt                TEXT,
                sample_collection_date TEXT,
                co_medications         TEXT,
                scheme                 INTEGER,
                trough                 TEXT,
                prepared_by_id         INTEGER REFERENCES doctors(id),
                checked_by_id          INTEGER REFERENCES doctors(id)
            );

            CREATE TABLE IF NOT EXISTS sample_points (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id     TEXT    NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                point_order   INTEGER NOT NULL,
                time_point    REAL    NOT NULL,
                concentration REAL    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pk_results (
                record_id      TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
                auc_0_last     REAL,
                auc_0_12       REAL,
                lambda_z       REAL,
                t_half         REAL,
                r_squared      REAL,
                t_last         REAL,
                c_trough       REAL,
                c_last         REAL,
                auc_lss        REAL,
                lss_equation   TEXT,
                interpretation TEXT
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS medications (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS drafts (
                id                     TEXT PRIMARY KEY,
                saved_at               TEXT NOT NULL,
                report_path            TEXT,
                sample_rows_json       TEXT,
                duration_options_json  TEXT,
                times_json             TEXT,
                concs_json             TEXT,
                name                   TEXT,
                age                    TEXT,
                sex                    TEXT,
                invoice_date           TEXT,
                invoice_number         TEXT,
                report_number          TEXT,
                dept                   TEXT,
                diagnosis              TEXT,
                tx_date                TEXT,
                delivery_date          TEXT,
                drug                   TEXT,
                preparation            TEXT,
                dose                   TEXT,
                dose_dt                TEXT,
                sample_collection_date TEXT,
                co_medications         TEXT,
                scheme                 INTEGER,
                trough                 TEXT,
                prepared_by_id         INTEGER REFERENCES doctors(id),
                checked_by_id          INTEGER REFERENCES doctors(id)
            );
        """)
        if not _column_exists(conn, "doctors", "type"):
            conn.execute("ALTER TABLE doctors ADD COLUMN type TEXT NOT NULL DEFAULT 'doctor'")

        # Migrations for patients
        if not _column_exists(conn, 'patients', 'pid'):
            conn.execute("ALTER TABLE patients ADD COLUMN pid TEXT")
        
        # Hospital number / Invoice number renames
        if _column_exists(conn, 'patients', 'hosp_no') and not _column_exists(conn, 'patients', 'invoice_number'):
            conn.execute("ALTER TABLE patients RENAME COLUMN hosp_no TO invoice_number")
        elif not _column_exists(conn, 'patients', 'invoice_number'):
            conn.execute("ALTER TABLE patients ADD COLUMN invoice_number TEXT")
            
        if _column_exists(conn, 'patients', 'weight') and not _column_exists(conn, 'patients', 'invoice_date'):
            conn.execute("ALTER TABLE patients RENAME COLUMN weight TO invoice_date")
        elif not _column_exists(conn, 'patients', 'invoice_date'):
            conn.execute("ALTER TABLE patients ADD COLUMN invoice_date TEXT")

        if _column_exists(conn, 'patients', 'ward') and not _column_exists(conn, 'patients', 'report_number'):
            conn.execute("ALTER TABLE patients RENAME COLUMN ward TO report_number")
        elif not _column_exists(conn, 'patients', 'report_number'):
            conn.execute("ALTER TABLE patients ADD COLUMN report_number TEXT")

        if not _column_exists(conn, 'patients', 'delivery_date'):
            conn.execute("ALTER TABLE patients ADD COLUMN delivery_date TEXT")

        # Migrations for records
        if not _column_exists(conn, 'records', 'report_path'):
            conn.execute("ALTER TABLE records ADD COLUMN report_path TEXT")
        if not _column_exists(conn, 'records', 'sample_rows_json'):
            conn.execute("ALTER TABLE records ADD COLUMN sample_rows_json TEXT")
        if not _column_exists(conn, 'records', 'duration_options_json'):
            conn.execute("ALTER TABLE records ADD COLUMN duration_options_json TEXT")
        if not _column_exists(conn, 'records', 'prepared_by_id'):
            conn.execute("ALTER TABLE records ADD COLUMN prepared_by_id INTEGER")
        if not _column_exists(conn, 'records', 'checked_by_id'):
            conn.execute("ALTER TABLE records ADD COLUMN checked_by_id INTEGER")

        # Migrations for drafts
        if not _column_exists(conn, 'drafts', 'report_path'):
            conn.execute("ALTER TABLE drafts ADD COLUMN report_path TEXT")
        if not _column_exists(conn, 'drafts', 'sample_rows_json'):
            conn.execute("ALTER TABLE drafts ADD COLUMN sample_rows_json TEXT")
        if not _column_exists(conn, 'drafts', 'duration_options_json'):
            conn.execute("ALTER TABLE drafts ADD COLUMN duration_options_json TEXT")
        if not _column_exists(conn, 'drafts', 'times_json'):
            conn.execute("ALTER TABLE drafts ADD COLUMN times_json TEXT")
        if not _column_exists(conn, 'drafts', 'concs_json'):
            conn.execute("ALTER TABLE drafts ADD COLUMN concs_json TEXT")
        
        # Draft fields renames
        if _column_exists(conn, 'drafts', 'hosp_no') and not _column_exists(conn, 'drafts', 'invoice_number'):
            conn.execute("ALTER TABLE drafts RENAME COLUMN hosp_no TO invoice_number")
        elif not _column_exists(conn, 'drafts', 'invoice_number'):
            conn.execute("ALTER TABLE drafts ADD COLUMN invoice_number TEXT")

        if _column_exists(conn, 'drafts', 'weight') and not _column_exists(conn, 'drafts', 'invoice_date'):
            conn.execute("ALTER TABLE drafts RENAME COLUMN weight TO invoice_date")
        elif not _column_exists(conn, 'drafts', 'invoice_date'):
            conn.execute("ALTER TABLE drafts ADD COLUMN invoice_date TEXT")

        if _column_exists(conn, 'drafts', 'ward') and not _column_exists(conn, 'drafts', 'report_number'):
            conn.execute("ALTER TABLE drafts RENAME COLUMN ward TO report_number")
        elif not _column_exists(conn, 'drafts', 'report_number'):
            conn.execute("ALTER TABLE drafts ADD COLUMN report_number TEXT")

        if not _column_exists(conn, 'drafts', 'delivery_date'):
            conn.execute("ALTER TABLE drafts ADD COLUMN delivery_date TEXT")
        if not _column_exists(conn, 'drafts', 'prepared_by_id'):
            conn.execute("ALTER TABLE drafts ADD COLUMN prepared_by_id INTEGER")
        if not _column_exists(conn, 'drafts', 'checked_by_id'):
            conn.execute("ALTER TABLE drafts ADD COLUMN checked_by_id INTEGER")

        # PK results migrations
        if not _column_exists(conn, 'pk_results', 'auc_lss'):
            conn.execute("ALTER TABLE pk_results ADD COLUMN auc_lss REAL")
        if not _column_exists(conn, 'pk_results', 'lss_equation'):
            conn.execute("ALTER TABLE pk_results ADD COLUMN lss_equation TEXT")

        conn.commit()
        _migrate_legacy_drafts(conn)

        for med in DEFAULT_MEDICATIONS_SEED:
            conn.execute("INSERT OR IGNORE INTO medications (name) VALUES (?)", (med,))
        
        # Seed doctors if empty
        if conn.execute("SELECT count(*) FROM doctors").fetchone()[0] == 0:
            conn.execute("INSERT INTO doctors (name, designation) VALUES (?, ?)", ("Dr. John Doe", "MBBS, MD (Nephrology)"))
            conn.execute("INSERT INTO doctors (name, designation) VALUES (?, ?)", ("Dr. Jane Smith", "MBBS, MS (Transplant Surgery)"))
        conn.commit()


# ─────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────

def _generate_pid() -> str:
    date_str = datetime.now().strftime("%Y%m%d")
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"PID-{date_str}-{suffix}"


def _get_or_create_patient(conn: sqlite3.Connection, patient: dict) -> int:
    invoice_no = patient.get('invoice_number', '') or ''
    # Reuse existing patient if invoice number is real
    if invoice_no and invoice_no != 'N/A':
        row = conn.execute(
            "SELECT id FROM patients WHERE invoice_number = ?", (invoice_no,)
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE patients
                   SET name = ?, age = ?, sex = ?, invoice_date = ?, report_number = ?, dept = ?,
                       diagnosis = ?, tx_date = ?, delivery_date = ?
                   WHERE id = ?""",
                (
                    patient.get('name'),
                    patient.get('age'),
                    patient.get('sex'),
                    patient.get('invoice_date'),
                    patient.get('report_number'),
                    patient.get('dept'),
                    patient.get('diag'),
                    patient.get('tx_date'),
                    patient.get('delivery_date'),
                    row['id'],
                )
            )
            return row['id']

    pid = _generate_pid()
    cursor = conn.execute(
        """INSERT INTO patients (pid, invoice_number, name, age, sex, invoice_date, report_number, dept, diagnosis, tx_date, delivery_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pid,
            invoice_no if invoice_no and invoice_no != 'N/A' else None,
            patient.get('name'),
            patient.get('age'),
            patient.get('sex'),
            patient.get('invoice_date'),
            patient.get('report_number'),
            patient.get('dept'),
            patient.get('diag'),
            patient.get('tx_date'),
            patient.get('delivery_date'),
        )
    )
    return cursor.lastrowid


def _row_to_snapshot(record: sqlite3.Row, points: list, pk_row) -> dict:
    """Reconstruct the snapshot dict format that tdm_report.py expects."""
    times = [p['time_point'] for p in points]
    concs = [p['concentration'] for p in points]

    patient = {
        'name':                   record['name']                   or 'N/A',
        'age':                    record['age']                    or 'N/A',
        'sex':                    record['sex']                    or '',
        'invoice_date':           record['invoice_date']           or '',
        'invoice_number':         record['invoice_number']         or 'N/A',
        'report_number':          record['report_number']          or 'N/A',
        'pid':                    record['pid']                    or 'N/A',
        'dept':                   record['dept']                   or 'N/A',
        'drug':                   record['drug']                   or '',
        'preparation':            record['preparation']            or '',
        'dose':                   record['dose']                   or '',
        'dose_dt':                record['dose_dt']                or '',
        'sample_collection_date': record['sample_collection_date'] or '',
        'diag':                   record['diagnosis']              or 'N/A',
        'tx_date':                record['tx_date']                or '',
        'delivery_date':          record['delivery_date']          or '',
        'med':                    record['co_medications']         or 'N/A',
    }

    snapshot = {
        'id':          record['id'],
        'saved_at':    record['saved_at'],
        'report_path': record['report_path'] or '',
        'record_type': record['record_type'],
        'patient':     patient,
        'scheme':      record['scheme'] or 4,
        'trough':      record['trough'] or '',
        'prepared_by_id': record['prepared_by_id'],
        'checked_by_id':  record['checked_by_id'],
        'times':       times,
        'concs':       concs,
    }

    if record['sample_rows_json']:
        try:
            snapshot['sample_rows'] = json.loads(record['sample_rows_json'])
        except Exception:
            snapshot['sample_rows'] = []
    if record['duration_options_json']:
        try:
            snapshot['duration_options'] = json.loads(record['duration_options_json'])
        except Exception:
            snapshot['duration_options'] = [snapshot['scheme']]

    if pk_row:
        snapshot['pk'] = {
            'auc_0_last': pk_row['auc_0_last'],
            'auc_0_12':   pk_row['auc_0_12'],
            'lambda_z':   pk_row['lambda_z'],
            't_half':     pk_row['t_half'],
            'r_squared':  pk_row['r_squared'],
            't_last':     pk_row['t_last'],
            'c_trough':   pk_row['c_trough'],
            'c_last':     pk_row['c_last'],
            'auc_lss':    pk_row['auc_lss'],
            'lss_equation': pk_row['lss_equation'],
        }
        snapshot['interp'] = pk_row['interpretation']

    return snapshot


def _draft_row_to_snapshot(row: sqlite3.Row) -> dict:
    patient = {
        'name':                   row['name']                   or 'N/A',
        'age':                    row['age']                    or 'N/A',
        'sex':                    row['sex']                    or '',
        'invoice_date':           row['invoice_date']           or '',
        'invoice_number':         row['invoice_number']         or 'N/A',
        'report_number':          row['report_number']          or 'N/A',
        'pid':                    'N/A',
        'dept':                   row['dept']                   or 'N/A',
        'drug':                   row['drug']                   or '',
        'preparation':            row['preparation']            or '',
        'dose':                   row['dose']                   or '',
        'dose_dt':                row['dose_dt']                or '',
        'sample_collection_date': row['sample_collection_date'] or '',
        'diag':                   row['diagnosis']              or 'N/A',
        'tx_date':                row['tx_date']                or '',
        'delivery_date':          row['delivery_date']          or '',
        'med':                    row['co_medications']         or 'N/A',
    }

    snapshot = {
        'id':          row['id'],
        'saved_at':    row['saved_at'],
        'report_path': row['report_path'] or '',
        'record_type': 'draft',
        'patient':     patient,
        'scheme':      row['scheme'] or 4,
        'trough':      row['trough'] or '',
        'prepared_by_id': row['prepared_by_id'],
        'checked_by_id':  row['checked_by_id'],
        'times':       [],
        'concs':       [],
    }

    if row['sample_rows_json']:
        try:
            snapshot['sample_rows'] = json.loads(row['sample_rows_json'])
        except Exception:
            snapshot['sample_rows'] = []
    if row['duration_options_json']:
        try:
            snapshot['duration_options'] = json.loads(row['duration_options_json'])
        except Exception:
            snapshot['duration_options'] = [snapshot['scheme']]
    if row['times_json']:
        try:
            snapshot['times'] = json.loads(row['times_json'])
        except Exception:
            snapshot['times'] = []
    if row['concs_json']:
        try:
            snapshot['concs'] = json.loads(row['concs_json'])
        except Exception:
            snapshot['concs'] = []
    return snapshot


def _save_draft(conn: sqlite3.Connection, snapshot: dict):
    patient = snapshot.get('patient', {})
    conn.execute(
        """INSERT OR REPLACE INTO drafts
           (id, saved_at, report_path, sample_rows_json, duration_options_json, times_json, concs_json,
            name, age, sex, invoice_date, invoice_number, report_number, dept, diagnosis, tx_date, delivery_date,
            drug, preparation, dose, dose_dt, sample_collection_date, co_medications, scheme, trough, prepared_by_id, checked_by_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            snapshot['id'],
            snapshot.get('saved_at', datetime.now().strftime("%d/%m/%Y")),
            snapshot.get('report_path'),
            json.dumps(snapshot.get('sample_rows', [])),
            json.dumps(snapshot.get('duration_options', [snapshot.get('scheme', 4)])),
            json.dumps(snapshot.get('times', [])),
            json.dumps(snapshot.get('concs', [])),
            patient.get('name'),
            patient.get('age'),
            patient.get('sex'),
            patient.get('invoice_date'),
            patient.get('invoice_number'),
            patient.get('report_number'),
            patient.get('dept'),
            patient.get('diag'),
            patient.get('tx_date'),
            patient.get('delivery_date'),
            patient.get('drug'),
            patient.get('preparation'),
            patient.get('dose'),
            patient.get('dose_dt'),
            patient.get('sample_collection_date'),
            patient.get('med'),
            snapshot.get('scheme'),
            snapshot.get('trough'),
            snapshot.get('prepared_by_id'),
            snapshot.get('checked_by_id'),
        )
    )


def _migrate_legacy_drafts(conn: sqlite3.Connection):
    try:
        legacy_drafts = conn.execute("""
            SELECT r.id, r.saved_at, r.report_path, r.sample_rows_json, r.duration_options_json,
                   r.drug, r.preparation, r.dose, r.dose_dt, r.sample_collection_date,
                   r.co_medications, r.scheme, r.trough,
                   p.invoice_number, p.name, p.age, p.sex, p.invoice_date, p.report_number, p.dept, p.diagnosis, p.tx_date, p.delivery_date
            FROM records r
            LEFT JOIN patients p ON r.patient_id = p.id
            WHERE r.record_type = 'draft'
        """).fetchall()
        for row in legacy_drafts:
            points = conn.execute(
                """SELECT time_point, concentration FROM sample_points
                   WHERE record_id = ? ORDER BY point_order""",
                (row['id'],)
            ).fetchall()
            times = [p['time_point'] for p in points]
            concs = [p['concentration'] for p in points]
            snapshot = {
                'id': row['id'],
                'saved_at': row['saved_at'],
                'report_path': row['report_path'] or '',
                'record_type': 'draft',
                'patient': {
                    'name': row['name'] or 'N/A',
                    'age': row['age'] or 'N/A',
                    'sex': row['sex'] or '',
                    'invoice_date': row['invoice_date'] or '',
                    'invoice_number': row['invoice_number'] or 'N/A',
                    'report_number': row['report_number'] or 'N/A',
                    'dept': row['dept'] or 'N/A',
                    'diag': row['diagnosis'] or 'N/A',
                    'tx_date': row['tx_date'] or '',
                    'delivery_date': row['delivery_date'] or '',
                    'drug': row['drug'] or '',
                    'preparation': row['preparation'] or '',
                    'dose': row['dose'] or '',
                    'dose_dt': row['dose_dt'] or '',
                    'sample_collection_date': row['sample_collection_date'] or '',
                    'med': row['co_medications'] or 'N/A',
                },
                'scheme': row['scheme'] or 4,
                'trough': row['trough'] or '',
                'times': times,
                'concs': concs,
            }
            if row['sample_rows_json']:
                try: snapshot['sample_rows'] = json.loads(row['sample_rows_json'])
                except: pass
            if row['duration_options_json']:
                try: snapshot['duration_options'] = json.loads(row['duration_options_json'])
                except: pass

            _save_draft(conn, snapshot)
            conn.execute("DELETE FROM records WHERE id = ?", (row['id'],))
    except Exception:
        pass


# ─────────────────────────────────────────
# Public API
# ─────────────────────────────────────────

def save_record(snapshot: dict, record_type: str = 'sample'):
    """Insert or replace a record and all its related data."""
    if record_type == 'draft':
        with _connect() as conn:
            _save_draft(conn, snapshot)
        return

    patient = snapshot.get('patient', {})

    with _connect() as conn:
        patient_id = _get_or_create_patient(conn, patient)

        conn.execute(
            """INSERT OR REPLACE INTO records
               (id, patient_id, record_type, saved_at, report_path, sample_rows_json, duration_options_json,
                drug, preparation, dose, dose_dt,
                sample_collection_date, co_medications, scheme, trough, prepared_by_id, checked_by_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot['id'],
                patient_id,
                record_type,
                snapshot.get('saved_at', datetime.now().strftime("%d/%m/%Y")),
                snapshot.get('report_path'),
                json.dumps(snapshot.get('sample_rows', [])),
                json.dumps(snapshot.get('duration_options', [snapshot.get('scheme', 4)])),
                patient.get('drug'),
                patient.get('preparation'),
                patient.get('dose'),
                patient.get('dose_dt'),
                patient.get('sample_collection_date'),
                patient.get('med'),
                snapshot.get('scheme'),
                snapshot.get('trough'),
                snapshot.get('prepared_by_id'),
                snapshot.get('checked_by_id'),
            )
        )

        # Replace sample points
        conn.execute("DELETE FROM sample_points WHERE record_id = ?", (snapshot['id'],))
        for i, (t, c) in enumerate(zip(snapshot.get('times', []), snapshot.get('concs', []))):
            conn.execute(
                """INSERT INTO sample_points (record_id, point_order, time_point, concentration)
                   VALUES (?, ?, ?, ?)""",
                (snapshot['id'], i, t, c)
            )

        # PK results
        pk = snapshot.get('pk')
        if pk:
            conn.execute(
                """INSERT OR REPLACE INTO pk_results
                   (record_id, auc_0_last, auc_0_12, lambda_z, t_half,
                    r_squared, t_last, c_trough, c_last, auc_lss, lss_equation, interpretation)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot['id'],
                    pk.get('auc_0_last'),
                    pk.get('auc_0_12'),
                    pk.get('lambda_z'),
                    pk.get('t_half'),
                    pk.get('r_squared'),
                    pk.get('t_last'),
                    pk.get('c_trough'),
                    pk.get('c_last'),
                    pk.get('auc_lss'),
                    pk.get('lss_equation'),
                    snapshot.get('interp'),
                )
            )
        else:
            conn.execute("DELETE FROM pk_results WHERE record_id = ?", (snapshot['id'],))


def delete_record(record_id: str):
    """Delete a record and cascade to sample_points and pk_results."""
    with _connect() as conn:
        conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
        conn.execute("DELETE FROM drafts WHERE id = ?", (record_id,))


def load_all() -> tuple[list, list]:
    """Return (samples, drafts) as lists of snapshot dicts."""
    with _connect() as conn:
        records = conn.execute("""
            SELECT r.id, r.record_type, r.saved_at, r.report_path, r.sample_rows_json, r.duration_options_json, r.drug, r.preparation,
                   r.dose, r.dose_dt, r.sample_collection_date, r.co_medications,
                   r.scheme, r.trough, r.prepared_by_id, r.checked_by_id,
                   p.pid, p.invoice_number, p.name, p.age, p.sex, p.invoice_date,
                   p.report_number, p.dept, p.diagnosis, p.tx_date, p.delivery_date
            FROM   records r
            LEFT JOIN patients p ON r.patient_id = p.id
            ORDER  BY r.saved_at ASC, r.id ASC
        """).fetchall()

        all_points = conn.execute(
            "SELECT record_id, time_point, concentration FROM sample_points ORDER BY record_id, point_order"
        ).fetchall()
        points_by_id: dict = {}
        for p in all_points:
            points_by_id.setdefault(p['record_id'], []).append(p)

        all_pk = conn.execute("SELECT * FROM pk_results").fetchall()
        pk_by_id = {r['record_id']: r for r in all_pk}

        samples = []
        for rec in records:
            if rec['record_type'] != 'sample': continue
            snapshot = _row_to_snapshot(rec, points_by_id.get(rec['id'], []), pk_by_id.get(rec['id']))
            samples.append(snapshot)

        draft_rows = conn.execute("""
            SELECT id, saved_at, report_path, sample_rows_json, duration_options_json, times_json, concs_json,
                   name, age, sex, invoice_date, invoice_number, report_number, dept, diagnosis, tx_date, delivery_date,
                   drug, preparation, dose, dose_dt, sample_collection_date, co_medications, scheme, trough, prepared_by_id, checked_by_id
            FROM drafts
            ORDER BY saved_at ASC, id ASC
        """).fetchall()
        drafts = [_draft_row_to_snapshot(row) for row in draft_rows]

        return samples, drafts


def load_duration_options(default_options: list[int]) -> list[int]:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = 'duration_options'").fetchone()
        if not row or not row['value']: return list(default_options)
        try:
            data = json.loads(row['value'])
            cleaned = []
            for item in data:
                try:
                    value = int(item)
                    if value > 0 and value not in cleaned: cleaned.append(value)
                except: continue
            return cleaned or list(default_options)
        except: return list(default_options)


def save_duration_options(options: list[int]):
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('duration_options', ?)", (json.dumps(options),))


def load_medications() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT name FROM medications ORDER BY LOWER(name) ASC").fetchall()
        return [row["name"] for row in rows]


def add_medication(name: str) -> bool:
    name = name.strip()
    if not name: return False
    with _connect() as conn:
        existing = conn.execute("SELECT name FROM medications WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
        if existing: return False
        cur = conn.execute("INSERT INTO medications (name) VALUES (?)", (name,))
        return cur.rowcount > 0


def update_medication(old_name: str, new_name: str) -> bool:
    new_name = new_name.strip()
    if not new_name: return False
    with _connect() as conn:
        existing = conn.execute("SELECT name FROM medications WHERE name = ? COLLATE NOCASE AND name != ?", (new_name, old_name)).fetchone()
        if existing: return False
        conn.execute("UPDATE medications SET name = ? WHERE name = ?", (new_name, old_name))
        return True


def delete_medication(name: str):
    with _connect() as conn:
        conn.execute("DELETE FROM medications WHERE name = ?", (name,))


def load_doctors() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM doctors ORDER BY LOWER(name) ASC").fetchall()
        return [dict(row) for row in rows]


def get_doctor_by_id(doctor_id: int) -> dict | None:
    if not doctor_id: return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
        return dict(row) if row else None


def add_doctor(name: str, designation: str, signature_path: str = None, type: str = 'doctor') -> int:
    with _connect() as conn:
        cur = conn.execute("INSERT INTO doctors (name, designation, signature_path, type) VALUES (?, ?, ?, ?)", (name, designation, signature_path, type))
        return cur.lastrowid


def update_doctor(doctor_id: int, name: str, designation: str, signature_path: str = None, type: str = 'doctor'):
    with _connect() as conn:
        conn.execute("UPDATE doctors SET name = ?, designation = ?, signature_path = ?, type = ? WHERE id = ?", (name, designation, signature_path, type, doctor_id))


def delete_doctor(doctor_id: int):
    with _connect() as conn:
        conn.execute("DELETE FROM doctors WHERE id = ?", (doctor_id,))


def migrate_from_json(json_path: Path):
    if not json_path.exists(): return
    try:
        data = json.loads(json_path.read_text())
        samples = data if isinstance(data, list) else data.get('samples', [])
        drafts  = [] if isinstance(data, list) else data.get('drafts', [])
        for snapshot in samples:
            try: save_record(snapshot, 'sample')
            except: pass
        for snapshot in drafts:
            try: save_record(snapshot, 'draft')
            except: pass
        json_path.rename(json_path.with_suffix('.json.bak'))
    except: pass
