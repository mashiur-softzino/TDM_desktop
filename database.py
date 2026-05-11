"""
TDM Report — Database layer (PostgreSQL)
"""

import json
import mimetypes
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

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

DEFAULT_REPORT_PRINT_CONFIG = {
    "mode": "custom",
    "custom_top_gap_cm": 2.3,
}

DEFAULT_SIGNATORY_SEED_FILE = "seed_signatories.json"


# ─────────────────────────────────────────
# Connection
# ─────────────────────────────────────────

class _ConnWrapper:
    """Thin wrapper around a psycopg2 connection."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return cur

    def executescript(self, sql):
        cur = self._conn.cursor()
        for stmt in sql.split(';'):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
        cur.close()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()


def _connect() -> _ConnWrapper:
    env_url = os.environ.get("TDM_DB_URL")
    if env_url:
        conn = psycopg2.connect(env_url)
    else:
        from db_config import load_db_config
        c = load_db_config()
        conn = psycopg2.connect(
            host=c['host'],
            port=int(c.get('port', 5432)),
            dbname=c['database'],
            user=c['username'],
            password=c['password'] or None,
            connect_timeout=5,
        )
    return _ConnWrapper(conn)


def _asset_base_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _load_default_signatories() -> list:
    seed_path = _asset_base_dir() / DEFAULT_SIGNATORY_SEED_FILE
    if not seed_path.exists():
        return []
    try:
        data = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _seed_default_signatories(conn) -> int:
    inserted = 0
    for item in _load_default_signatories():
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        phone = str(item.get("phone") or "").strip() or None
        signatory_type = str(item.get("type") or "doctor").strip() or "doctor"
        designation = str(item.get("designation") or "").strip()
        existing = None
        if phone:
            existing = conn.execute(
                "SELECT id FROM signatories WHERE phone = %s",
                (phone,)
            ).fetchone()
        if existing is None:
            existing = conn.execute(
                "SELECT id FROM signatories WHERE lower(name) = lower(%s) AND type = %s",
                (name, signatory_type)
            ).fetchone()
        if existing is not None:
            continue

        signature_path = str(item.get("signature_file") or "").strip()
        signature_data = None
        signature_mime = None
        if signature_path:
            path = _asset_base_dir() / signature_path
            try:
                if path.exists() and path.stat().st_size <= 2 * 1024 * 1024:
                    signature_data = path.read_bytes()
                    signature_mime = mimetypes.guess_type(str(path))[0] or "image/png"
            except OSError:
                signature_data = None
                signature_mime = None

        conn.execute(
            """INSERT INTO signatories
               (name, designation, signature_path, signature_data, signature_mime, type, phone, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)""",
            (
                name,
                designation,
                signature_path or None,
                psycopg2.Binary(signature_data) if signature_data else None,
                signature_mime,
                signatory_type,
                phone,
            )
        )
        inserted += 1
    return inserted


def test_db_connection() -> str | None:
    """Returns None on success, error message on failure."""
    try:
        with _connect() as conn:
            conn.execute("SELECT 1")
        return None
    except Exception as e:
        return str(e)


# ─────────────────────────────────────────
# Backup stubs (PostgreSQL handles its own backups)
# ─────────────────────────────────────────

def create_database_backup(reason: str = "manual") -> None:
    return None


def restore_latest_database_backup() -> None:
    return None


# ─────────────────────────────────────────
# Schema
# ─────────────────────────────────────────

def _parse_duration_options(value, default_options: list) -> list:
    if not value:
        return list(default_options)
    try:
        data = json.loads(value)
        cleaned = []
        for item in data:
            try:
                option = int(item)
                if option > 0 and option not in cleaned:
                    cleaned.append(option)
            except Exception:
                continue
        return cleaned or list(default_options)
    except Exception:
        return list(default_options)


def _ensure_legacy_schema_compat(conn) -> None:
    """Add columns needed by older installed databases."""
    legacy_columns = [
        "ALTER TABLE signatories ADD COLUMN IF NOT EXISTS signature_data BYTEA",
        "ALTER TABLE signatories ADD COLUMN IF NOT EXISTS signature_mime TEXT",
        "ALTER TABLE signatories ADD COLUMN IF NOT EXISTS type TEXT NOT NULL DEFAULT 'doctor'",
        "ALTER TABLE signatories ADD COLUMN IF NOT EXISTS phone TEXT",
        "ALTER TABLE signatories ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE records ADD COLUMN IF NOT EXISTS prepared_by_id INTEGER REFERENCES signatories(id)",
        "ALTER TABLE records ADD COLUMN IF NOT EXISTS checked_by_id INTEGER REFERENCES signatories(id)",
        "ALTER TABLE drafts ADD COLUMN IF NOT EXISTS prepared_by_id INTEGER REFERENCES signatories(id)",
        "ALTER TABLE drafts ADD COLUMN IF NOT EXISTS checked_by_id INTEGER REFERENCES signatories(id)",
    ]
    for sql in legacy_columns:
        conn.execute(sql)


def _migrate_legacy_signature_files(conn) -> None:
    legacy_sigs = conn.execute(
        """SELECT id, signature_path
           FROM signatories
           WHERE signature_data IS NULL
             AND signature_path IS NOT NULL
             AND signature_path <> ''"""
    ).fetchall()
    for sig in legacy_sigs:
        path = Path(sig['signature_path'])
        try:
            if not path.exists() or path.stat().st_size > 2 * 1024 * 1024:
                continue
            data = path.read_bytes()
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
            conn.execute(
                """UPDATE signatories
                   SET signature_data = %s, signature_mime = %s
                   WHERE id = %s""",
                (psycopg2.Binary(data), mime, sig['id'])
            )
        except OSError:
            continue


def init_db(default_duration_options: list | None = None):
    """Create tables if they don't exist.

    When default_duration_options is provided, returns the saved duration options
    using the same startup connection.
    """
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS patients (
                id             SERIAL PRIMARY KEY,
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
                delivery_date  TEXT,
                phone          TEXT
            );

            CREATE TABLE IF NOT EXISTS signatories (
                id             SERIAL PRIMARY KEY,
                name           TEXT NOT NULL,
                designation    TEXT,
                signature_path TEXT,
                signature_data BYTEA,
                signature_mime TEXT,
                type           TEXT NOT NULL DEFAULT 'doctor',
                phone          TEXT,
                is_active      BOOLEAN NOT NULL DEFAULT TRUE
            );

            CREATE TABLE IF NOT EXISTS records (
                id                     SERIAL PRIMARY KEY,
                patient_id             INTEGER REFERENCES patients(id),
                record_type            TEXT NOT NULL DEFAULT 'sample',
                saved_at               TEXT NOT NULL,
                report_path            TEXT,
                sampling_mode          TEXT NOT NULL DEFAULT 'multi',
                direct_auc             TEXT,
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
                prepared_by_id         INTEGER REFERENCES signatories(id),
                checked_by_id          INTEGER REFERENCES signatories(id)
            );

            CREATE TABLE IF NOT EXISTS sample_points (
                id            SERIAL PRIMARY KEY,
                record_id     INTEGER          NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                point_order   INTEGER          NOT NULL,
                time_point    DOUBLE PRECISION NOT NULL,
                concentration DOUBLE PRECISION NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pk_results (
                record_id      INTEGER PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
                auc_0_last     DOUBLE PRECISION,
                auc_0_12       DOUBLE PRECISION,
                lambda_z       DOUBLE PRECISION,
                t_half         DOUBLE PRECISION,
                r_squared      DOUBLE PRECISION,
                t_last         DOUBLE PRECISION,
                c_trough       DOUBLE PRECISION,
                c_last         DOUBLE PRECISION,
                auc_lss        DOUBLE PRECISION,
                lss_equation   TEXT,
                interpretation TEXT
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS medications (
                id   SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS drafts (
                id                     SERIAL PRIMARY KEY,
                saved_at               TEXT NOT NULL,
                report_path            TEXT,
                sampling_mode          TEXT NOT NULL DEFAULT 'multi',
                direct_auc             TEXT,
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
                phone                  TEXT,
                prepared_by_id         INTEGER REFERENCES signatories(id),
                checked_by_id          INTEGER REFERENCES signatories(id)
            )
        """)
        _ensure_legacy_schema_compat(conn)
        _migrate_legacy_signature_files(conn)
        for med in DEFAULT_MEDICATIONS_SEED:
            conn.execute(
                "INSERT INTO medications (name) VALUES (%s) ON CONFLICT DO NOTHING",
                (med,)
            )

        _seed_default_signatories(conn)
        conn.commit()
        if default_duration_options is None:
            return None
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'duration_options'"
        ).fetchone()
        return _parse_duration_options(
            row['value'] if row else None,
            default_duration_options,
        )


# ─────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────

def _generate_pid(conn) -> str:
    date_prefix = datetime.now().strftime("%y%m%d")
    prefix = f"PID-{date_prefix}"
    rows = conn.execute(
        "SELECT pid FROM patients WHERE pid LIKE %s",
        (f"{prefix}%",),
    ).fetchall()

    next_serial = 1
    for row in rows:
        pid = row.get("pid") or ""
        suffix = pid.removeprefix(prefix)
        if not suffix.isdigit():
            continue
        next_serial = max(next_serial, int(suffix) + 1)

    return f"{prefix}{next_serial}"


def _get_or_create_patient(conn, patient: dict, existing_patient_id: int | None = None) -> int:
    if existing_patient_id is not None:
        row = conn.execute(
            "SELECT id FROM patients WHERE id = %s", (existing_patient_id,)
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE patients
                   SET name = %s, age = %s, sex = %s, invoice_date = %s, report_number = %s,
                       dept = %s, diagnosis = %s, tx_date = %s, delivery_date = %s, phone = %s
                   WHERE id = %s""",
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
                    patient.get('phone'),
                    row['id'],
                )
            )
            return row['id']

    invoice_no = patient.get('invoice_number', '') or ''
    if invoice_no and invoice_no != 'N/A':
        row = conn.execute(
            "SELECT id FROM patients WHERE invoice_number = %s", (invoice_no,)
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE patients
                   SET name = %s, age = %s, sex = %s, invoice_date = %s, report_number = %s,
                       dept = %s, diagnosis = %s, tx_date = %s, delivery_date = %s, phone = %s
                   WHERE id = %s""",
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
                    patient.get('phone'),
                    row['id'],
                )
            )
            return row['id']

    pid = _generate_pid(conn)
    cur = conn.execute(
        """INSERT INTO patients
               (pid, invoice_number, name, age, sex, invoice_date, report_number,
                dept, diagnosis, tx_date, delivery_date, phone)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
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
            patient.get('phone'),
        )
    )
    return cur.fetchone()['id']


def _row_to_snapshot(record, points: list, pk_row) -> dict:
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
        'phone':                  record['phone']                  or 'N/A',
    }

    snapshot = {
        'id':          record['id'],
        'patient_db_id': record['patient_id'],
        'saved_at':    record['saved_at'],
        'report_path': record['report_path'] or '',
        'record_type': record['record_type'],
        'patient':     patient,
        'sampling_mode': record['sampling_mode'] or 'multi',
        'direct_auc':  record['direct_auc'] or '',
        'scheme':      record['scheme'] or 4,
        'trough':      record['trough'] or '',
        'prepared_by_id': record['prepared_by_id'],
        'checked_by_id':  record['checked_by_id'],
        'times':          times,
        'concs':          concs,
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
            'auc_0_last':   pk_row['auc_0_last'],
            'auc_0_12':     pk_row['auc_0_12'],
            'lambda_z':     pk_row['lambda_z'],
            't_half':       pk_row['t_half'],
            'r_squared':    pk_row['r_squared'],
            't_last':       pk_row['t_last'],
            'c_trough':     pk_row['c_trough'],
            'c_last':       pk_row['c_last'],
            'auc_lss':      pk_row['auc_lss'],
            'lss_equation': pk_row['lss_equation'],
        }
        snapshot['interp'] = pk_row['interpretation']

    return snapshot


def _draft_row_to_snapshot(row) -> dict:
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
        'phone':                  row['phone']                  or 'N/A',
    }

    snapshot = {
        'id':          row['id'],
        'saved_at':    row['saved_at'],
        'report_path': row['report_path'] or '',
        'record_type': 'draft',
        'patient':     patient,
        'sampling_mode': row['sampling_mode'] or 'multi',
        'direct_auc':  row['direct_auc'] or '',
        'scheme':      row['scheme'] or 4,
        'trough':      row['trough'] or '',
        'prepared_by_id': row['prepared_by_id'],
        'checked_by_id':  row['checked_by_id'],
        'times':          [],
        'concs':          [],
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


def _save_draft(conn, snapshot: dict):
    patient = snapshot.get('patient', {})
    prepared_by_id = snapshot.get('prepared_by_id') or None
    checked_by_id  = snapshot.get('checked_by_id')  or None
    params = (
        snapshot.get('saved_at', datetime.now().strftime("%d/%m/%Y")),
        snapshot.get('report_path'),
        snapshot.get('sampling_mode', 'multi'),
        snapshot.get('direct_auc', ''),
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
        patient.get('phone'),
        prepared_by_id,
        checked_by_id,
    )

    draft_id = snapshot.get('id')
    if draft_id is None:
        pass
    else:
        cur = conn.execute(
            """UPDATE drafts SET
                   saved_at               = %s,
                   report_path            = %s,
                   sampling_mode          = %s,
                   direct_auc             = %s,
                   sample_rows_json       = %s,
                   duration_options_json  = %s,
                   times_json             = %s,
                   concs_json             = %s,
                   name                   = %s,
                   age                    = %s,
                   sex                    = %s,
                   invoice_date           = %s,
                   invoice_number         = %s,
                   report_number          = %s,
                   dept                   = %s,
                   diagnosis              = %s,
                   tx_date                = %s,
                   delivery_date          = %s,
                   drug                   = %s,
                   preparation            = %s,
                   dose                   = %s,
                   dose_dt                = %s,
                   sample_collection_date = %s,
                   co_medications         = %s,
                   scheme                 = %s,
                   trough                 = %s,
                   phone                  = %s,
                   prepared_by_id         = %s,
                   checked_by_id          = %s
               WHERE id = %s""",
            params + (draft_id,),
        )
        if cur.rowcount:
            return draft_id

    cur = conn.execute(
        """INSERT INTO drafts
               (saved_at, report_path, sampling_mode, direct_auc, sample_rows_json,
                duration_options_json, times_json, concs_json, name, age, sex, invoice_date,
                invoice_number, report_number, dept, diagnosis, tx_date, delivery_date,
                drug, preparation, dose, dose_dt, sample_collection_date,
                co_medications, scheme, trough, phone, prepared_by_id, checked_by_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        params,
    )
    snapshot['id'] = cur.fetchone()['id']
    return snapshot['id']


# ─────────────────────────────────────────
# Public API
# ─────────────────────────────────────────

def save_record(snapshot: dict, record_type: str = 'sample'):
    if record_type == 'draft':
        with _connect() as conn:
            return _save_draft(conn, snapshot)

    patient        = snapshot.get('patient', {})
    prepared_by_id = snapshot.get('prepared_by_id') or None
    checked_by_id  = snapshot.get('checked_by_id')  or None

    with _connect() as conn:
        record_id = snapshot.get('id')
        patient_id = snapshot.get('patient_db_id')
        if patient_id is None and record_id is not None:
            row = conn.execute(
                "SELECT patient_id FROM records WHERE id = %s",
                (record_id,),
            ).fetchone()
            if row:
                patient_id = row['patient_id']

        patient_id = _get_or_create_patient(conn, patient, patient_id)
        snapshot['patient_db_id'] = patient_id
        row = conn.execute(
            "SELECT pid FROM patients WHERE id = %s",
            (patient_id,),
        ).fetchone()
        if row:
            patient['pid'] = row['pid'] or patient.get('pid') or 'N/A'

        params = (
            patient_id,
            record_type,
            snapshot.get('saved_at', datetime.now().strftime("%d/%m/%Y")),
            snapshot.get('report_path'),
            snapshot.get('sampling_mode', 'multi'),
            snapshot.get('direct_auc', ''),
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
            prepared_by_id,
            checked_by_id,
        )

        record_id = snapshot.get('id')
        if record_id is None:
            pass
        else:
            cur = conn.execute(
                """UPDATE records SET
                       patient_id             = %s,
                       record_type            = %s,
                       saved_at               = %s,
                       report_path            = %s,
                       sampling_mode          = %s,
                       direct_auc             = %s,
                       sample_rows_json       = %s,
                       duration_options_json  = %s,
                       drug                   = %s,
                       preparation            = %s,
                       dose                   = %s,
                       dose_dt                = %s,
                       sample_collection_date = %s,
                       co_medications         = %s,
                       scheme                 = %s,
                       trough                 = %s,
                       prepared_by_id         = %s,
                       checked_by_id          = %s
                   WHERE id = %s""",
                params + (record_id,),
            )
            if cur.rowcount:
                pass
            else:
                record_id = None

        if record_id is None:
            cur = conn.execute(
                """INSERT INTO records
                       (patient_id, record_type, saved_at, report_path, sampling_mode, direct_auc,
                        sample_rows_json, duration_options_json, drug, preparation, dose, dose_dt,
                        sample_collection_date, co_medications, scheme, trough, prepared_by_id, checked_by_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                params,
            )
            record_id = cur.fetchone()['id']
            snapshot['id'] = record_id

        conn.execute("DELETE FROM sample_points WHERE record_id = %s", (record_id,))
        for i, (t, c) in enumerate(zip(snapshot.get('times', []), snapshot.get('concs', []))):
            conn.execute(
                """INSERT INTO sample_points (record_id, point_order, time_point, concentration)
                   VALUES (%s, %s, %s, %s)""",
                (record_id, i, t, c)
            )

        pk = snapshot.get('pk')
        if pk:
            conn.execute(
                """INSERT INTO pk_results
                       (record_id, auc_0_last, auc_0_12, lambda_z, t_half,
                        r_squared, t_last, c_trough, c_last, auc_lss, lss_equation, interpretation)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (record_id) DO UPDATE SET
                       auc_0_last     = EXCLUDED.auc_0_last,
                       auc_0_12       = EXCLUDED.auc_0_12,
                       lambda_z       = EXCLUDED.lambda_z,
                       t_half         = EXCLUDED.t_half,
                       r_squared      = EXCLUDED.r_squared,
                       t_last         = EXCLUDED.t_last,
                       c_trough       = EXCLUDED.c_trough,
                       c_last         = EXCLUDED.c_last,
                       auc_lss        = EXCLUDED.auc_lss,
                       lss_equation   = EXCLUDED.lss_equation,
                       interpretation = EXCLUDED.interpretation""",
                (
                    record_id,
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
            conn.execute("DELETE FROM pk_results WHERE record_id = %s", (record_id,))
        return record_id


def delete_record(record_id: int):
    with _connect() as conn:
        conn.execute("DELETE FROM records WHERE id = %s", (record_id,))
        conn.execute("DELETE FROM drafts WHERE id = %s", (record_id,))


def load_all() -> tuple[list, list]:
    with _connect() as conn:
        records = conn.execute("""
            SELECT r.id, r.patient_id, r.record_type, r.saved_at, r.report_path, r.sampling_mode, r.direct_auc, r.sample_rows_json, r.duration_options_json, r.drug, r.preparation,
                   r.dose, r.dose_dt, r.sample_collection_date, r.co_medications,
                   r.scheme, r.trough, r.prepared_by_id, r.checked_by_id,
                   p.pid, p.invoice_number, p.name, p.age, p.sex, p.invoice_date,
                   p.report_number, p.dept, p.diagnosis, p.tx_date, p.delivery_date, p.phone
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
            if rec['record_type'] != 'sample':
                continue
            snapshot = _row_to_snapshot(rec, points_by_id.get(rec['id'], []), pk_by_id.get(rec['id']))
            samples.append(snapshot)

        draft_rows = conn.execute("""
            SELECT id, saved_at, report_path, sampling_mode, direct_auc, sample_rows_json, duration_options_json, times_json, concs_json,
                   name, age, sex, invoice_date, invoice_number, report_number, dept, diagnosis, tx_date, delivery_date,
                    drug, preparation, dose, dose_dt, sample_collection_date, co_medications, scheme, trough, phone, prepared_by_id, checked_by_id
            FROM drafts
            ORDER BY saved_at ASC, id ASC
        """).fetchall()
        drafts = [_draft_row_to_snapshot(row) for row in draft_rows]

        return samples, drafts


def load_duration_options(default_options: list) -> list:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'duration_options'"
        ).fetchone()
        return _parse_duration_options(row['value'] if row else None, default_options)


def save_duration_options(options: list):
    with _connect() as conn:
        conn.execute(
            """INSERT INTO app_settings (key, value) VALUES ('duration_options', %s)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            (json.dumps(options),)
        )


def load_report_print_config() -> dict:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'report_print_config'"
        ).fetchone()
    config = DEFAULT_REPORT_PRINT_CONFIG.copy()
    if row:
        try:
            saved = json.loads(row['value'] or "{}")
            if isinstance(saved, dict):
                config.update(saved)
        except (TypeError, ValueError):
            pass
    if config.get("mode") not in {"normal", "custom"}:
        config["mode"] = DEFAULT_REPORT_PRINT_CONFIG["mode"]
        config["custom_top_gap_cm"] = DEFAULT_REPORT_PRINT_CONFIG["custom_top_gap_cm"]
    try:
        gap = float(config.get("custom_top_gap_cm", DEFAULT_REPORT_PRINT_CONFIG["custom_top_gap_cm"]))
    except (TypeError, ValueError):
        gap = DEFAULT_REPORT_PRINT_CONFIG["custom_top_gap_cm"]
    config["custom_top_gap_cm"] = max(0.0, min(gap, 10.0))
    return config


def save_report_print_config(config: dict):
    mode = config.get("mode", DEFAULT_REPORT_PRINT_CONFIG["mode"])
    if mode not in {"normal", "custom"}:
        mode = DEFAULT_REPORT_PRINT_CONFIG["mode"]
    try:
        gap = float(config.get("custom_top_gap_cm", DEFAULT_REPORT_PRINT_CONFIG["custom_top_gap_cm"]))
    except (TypeError, ValueError):
        gap = DEFAULT_REPORT_PRINT_CONFIG["custom_top_gap_cm"]
    saved = {
        "mode": mode,
        "custom_top_gap_cm": max(0.0, min(gap, 10.0)),
    }
    with _connect() as conn:
        conn.execute(
            """INSERT INTO app_settings (key, value) VALUES ('report_print_config', %s)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            (json.dumps(saved),)
        )


def load_medications() -> list:
    with _connect() as conn:
        rows = conn.execute("SELECT name FROM medications ORDER BY lower(name) ASC").fetchall()
        return [row['name'] for row in rows]


def add_medication(name: str) -> bool:
    name = name.strip()
    if not name:
        return False
    with _connect() as conn:
        existing = conn.execute(
            "SELECT name FROM medications WHERE lower(name) = lower(%s)", (name,)
        ).fetchone()
        if existing:
            return False
        cur = conn.execute("INSERT INTO medications (name) VALUES (%s)", (name,))
        return cur.rowcount > 0


def update_medication(old_name: str, new_name: str) -> bool:
    new_name = new_name.strip()
    if not new_name:
        return False
    with _connect() as conn:
        existing = conn.execute(
            "SELECT name FROM medications WHERE lower(name) = lower(%s) AND name != %s",
            (new_name, old_name)
        ).fetchone()
        if existing:
            return False
        conn.execute("UPDATE medications SET name = %s WHERE name = %s", (new_name, old_name))
        return True


def delete_medication(name: str):
    with _connect() as conn:
        conn.execute("DELETE FROM medications WHERE name = %s", (name,))


def load_signatories(include_inactive: bool = False) -> list:
    with _connect() as conn:
        if include_inactive:
            rows = conn.execute("SELECT * FROM signatories ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM signatories WHERE is_active = TRUE ORDER BY id DESC"
            ).fetchall()
        return [dict(row) for row in rows]


def get_signatory_by_id(signatory_id: int) -> dict | None:
    if not signatory_id:
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM signatories WHERE id = %s", (signatory_id,)).fetchone()
        return dict(row) if row else None


def is_signatory_phone_exists(phone: str, exclude_id: int = None) -> bool:
    if not phone:
        return False
    with _connect() as conn:
        if exclude_id:
            row = conn.execute(
                "SELECT 1 FROM signatories WHERE phone = %s AND id != %s AND is_active = TRUE",
                (phone, exclude_id)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM signatories WHERE phone = %s AND is_active = TRUE",
                (phone,)
            ).fetchone()
        return row is not None


def add_signatory(name: str, designation: str, signature_path: str = None,
                  type: str = 'doctor', phone: str = None,
                  signature_data: bytes | None = None,
                  signature_mime: str | None = None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO signatories
               (name, designation, signature_path, signature_data, signature_mime, type, phone)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (name, designation, signature_path, psycopg2.Binary(signature_data) if signature_data else None,
             signature_mime, type, phone)
        )
        return cur.fetchone()['id']


def update_signatory(signatory_id: int, name: str, designation: str,
                     signature_path: str = None, type: str = 'doctor', phone: str = None,
                     signature_data: bytes | None = None,
                     signature_mime: str | None = None):
    with _connect() as conn:
        conn.execute(
            """UPDATE signatories
               SET name = %s, designation = %s, signature_path = %s,
                   signature_data = %s, signature_mime = %s, type = %s, phone = %s
               WHERE id = %s""",
            (name, designation, signature_path,
             psycopg2.Binary(signature_data) if signature_data else None,
             signature_mime, type, phone, signatory_id)
        )


def set_signatory_active(signatory_id: int, is_active: bool):
    with _connect() as conn:
        conn.execute(
            "UPDATE signatories SET is_active = %s WHERE id = %s",
            (is_active, signatory_id)
        )


