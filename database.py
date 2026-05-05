"""
TDM Report — Database layer (PostgreSQL)
"""

import json
import os
import random
import string
from pathlib import Path
from datetime import datetime

import psycopg2
import psycopg2.extras

from app_paths import ensure_data_dirs
from db_config import get_db_url

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


# ─────────────────────────────────────────
# Connection
# ─────────────────────────────────────────

class _ConnWrapper:
    """Thin wrapper around a psycopg2 connection that mimics the SQLite interface."""

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
            if stmt and not stmt.upper().startswith('PRAGMA'):
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
        )
    return _ConnWrapper(conn)


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

def _column_exists(conn, table: str, column: str) -> bool:
    cur = conn.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s AND column_name = %s""",
        (table, column)
    )
    return cur.fetchone() is not None


def init_db():
    """Create tables if they don't exist."""
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

            CREATE TABLE IF NOT EXISTS doctors (
                id             SERIAL PRIMARY KEY,
                name           TEXT NOT NULL,
                designation    TEXT,
                signature_path TEXT,
                type           TEXT NOT NULL DEFAULT 'doctor',
                phone          TEXT
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
                id            SERIAL PRIMARY KEY,
                record_id     TEXT             NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                point_order   INTEGER          NOT NULL,
                time_point    DOUBLE PRECISION NOT NULL,
                concentration DOUBLE PRECISION NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pk_results (
                record_id      TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
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
                phone                  TEXT,
                prepared_by_id         INTEGER REFERENCES doctors(id),
                checked_by_id          INTEGER REFERENCES doctors(id)
            )
        """)

        # Migrations for existing databases
        for col in ('auc_lss',):
            if not _column_exists(conn, 'pk_results', col):
                conn.execute(f"ALTER TABLE pk_results ADD COLUMN {col} DOUBLE PRECISION")
        for col in ('lss_equation', 'interpretation'):
            if not _column_exists(conn, 'pk_results', col):
                conn.execute(f"ALTER TABLE pk_results ADD COLUMN {col} TEXT")
        if not _column_exists(conn, 'patients', 'phone'):
            conn.execute("ALTER TABLE patients ADD COLUMN phone TEXT")
        if not _column_exists(conn, 'drafts', 'phone'):
            conn.execute("ALTER TABLE drafts ADD COLUMN phone TEXT")
        if not _column_exists(conn, 'doctors', 'phone'):
            conn.execute("ALTER TABLE doctors ADD COLUMN phone TEXT")

        conn.commit()
        _migrate_legacy_drafts(conn)

        for med in DEFAULT_MEDICATIONS_SEED:
            conn.execute(
                "INSERT INTO medications (name) VALUES (%s) ON CONFLICT DO NOTHING",
                (med,)
            )

        cur = conn.execute("SELECT count(*) FROM doctors")
        row = cur.fetchone()
        if row and row['count'] == 0:
            conn.execute(
                "INSERT INTO doctors (name, designation) VALUES (%s, %s)",
                ("Dr. John Doe", "MBBS, MD (Nephrology)")
            )
            conn.execute(
                "INSERT INTO doctors (name, designation) VALUES (%s, %s)",
                ("Dr. Jane Smith", "MBBS, MS (Transplant Surgery)")
            )
        conn.commit()


# ─────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────

def _generate_pid() -> str:
    date_str = datetime.now().strftime("%Y%m%d")
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"PID-{date_str}-{suffix}"


def _get_or_create_patient(conn, patient: dict) -> int:
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

    pid = _generate_pid()
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
        'id':             record['id'],
        'saved_at':       record['saved_at'],
        'report_path':    record['report_path'] or '',
        'record_type':    record['record_type'],
        'patient':        patient,
        'scheme':         record['scheme'] or 4,
        'trough':         record['trough'] or '',
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
        'id':             row['id'],
        'saved_at':       row['saved_at'],
        'report_path':    row['report_path'] or '',
        'record_type':    'draft',
        'patient':        patient,
        'scheme':         row['scheme'] or 4,
        'trough':         row['trough'] or '',
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
    conn.execute(
        """INSERT INTO drafts
               (id, saved_at, report_path, sample_rows_json, duration_options_json,
                times_json, concs_json, name, age, sex, invoice_date, invoice_number,
                report_number, dept, diagnosis, tx_date, delivery_date,
                drug, preparation, dose, dose_dt, sample_collection_date,
                co_medications, scheme, trough, phone, prepared_by_id, checked_by_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (id) DO UPDATE SET
               saved_at               = EXCLUDED.saved_at,
               report_path            = EXCLUDED.report_path,
               sample_rows_json       = EXCLUDED.sample_rows_json,
               duration_options_json  = EXCLUDED.duration_options_json,
               times_json             = EXCLUDED.times_json,
               concs_json             = EXCLUDED.concs_json,
               name                   = EXCLUDED.name,
               age                    = EXCLUDED.age,
               sex                    = EXCLUDED.sex,
               invoice_date           = EXCLUDED.invoice_date,
               invoice_number         = EXCLUDED.invoice_number,
               report_number          = EXCLUDED.report_number,
               dept                   = EXCLUDED.dept,
               diagnosis              = EXCLUDED.diagnosis,
               tx_date                = EXCLUDED.tx_date,
               delivery_date          = EXCLUDED.delivery_date,
               drug                   = EXCLUDED.drug,
               preparation            = EXCLUDED.preparation,
               dose                   = EXCLUDED.dose,
               dose_dt                = EXCLUDED.dose_dt,
               sample_collection_date = EXCLUDED.sample_collection_date,
               co_medications         = EXCLUDED.co_medications,
               scheme                 = EXCLUDED.scheme,
               trough                 = EXCLUDED.trough,
               phone                  = EXCLUDED.phone,
               prepared_by_id         = EXCLUDED.prepared_by_id,
               checked_by_id          = EXCLUDED.checked_by_id""",
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
            patient.get('phone'),
            prepared_by_id,
            checked_by_id,
        )
    )


def _migrate_legacy_drafts(conn):
    try:
        legacy_drafts = conn.execute("""
            SELECT r.id, r.saved_at, r.report_path, r.sample_rows_json, r.duration_options_json,
                   r.drug, r.preparation, r.dose, r.dose_dt, r.sample_collection_date,
                   r.co_medications, r.scheme, r.trough,
                   p.invoice_number, p.name, p.age, p.sex, p.invoice_date,
                   p.report_number, p.dept, p.diagnosis, p.tx_date, p.delivery_date
            FROM records r
            LEFT JOIN patients p ON r.patient_id = p.id
            WHERE r.record_type = 'draft'
        """).fetchall()
        for row in legacy_drafts:
            points = conn.execute(
                """SELECT time_point, concentration FROM sample_points
                   WHERE record_id = %s ORDER BY point_order""",
                (row['id'],)
            ).fetchall()
            times = [p['time_point'] for p in points]
            concs = [p['concentration'] for p in points]
            snapshot = {
                'id':          row['id'],
                'saved_at':    row['saved_at'],
                'report_path': row['report_path'] or '',
                'record_type': 'draft',
                'patient': {
                    'name':                   row['name']          or 'N/A',
                    'age':                    row['age']           or 'N/A',
                    'sex':                    row['sex']           or '',
                    'invoice_date':           row['invoice_date']  or '',
                    'invoice_number':         row['invoice_number'] or 'N/A',
                    'report_number':          row['report_number'] or 'N/A',
                    'dept':                   row['dept']          or 'N/A',
                    'diag':                   row['diagnosis']     or 'N/A',
                    'tx_date':                row['tx_date']       or '',
                    'delivery_date':          row['delivery_date'] or '',
                    'drug':                   row['drug']          or '',
                    'preparation':            row['preparation']   or '',
                    'dose':                   row['dose']          or '',
                    'dose_dt':                row['dose_dt']       or '',
                    'sample_collection_date': row['sample_collection_date'] or '',
                    'med':                    row['co_medications'] or 'N/A',
                },
                'scheme': row['scheme'] or 4,
                'trough': row['trough'] or '',
                'times':  times,
                'concs':  concs,
            }
            if row['sample_rows_json']:
                try:
                    snapshot['sample_rows'] = json.loads(row['sample_rows_json'])
                except Exception:
                    pass
            if row['duration_options_json']:
                try:
                    snapshot['duration_options'] = json.loads(row['duration_options_json'])
                except Exception:
                    pass
            _save_draft(conn, snapshot)
            conn.execute("DELETE FROM records WHERE id = %s", (row['id'],))
    except Exception:
        pass


# ─────────────────────────────────────────
# Public API
# ─────────────────────────────────────────

def save_record(snapshot: dict, record_type: str = 'sample'):
    if record_type == 'draft':
        with _connect() as conn:
            _save_draft(conn, snapshot)
        return

    patient        = snapshot.get('patient', {})
    prepared_by_id = snapshot.get('prepared_by_id') or None
    checked_by_id  = snapshot.get('checked_by_id')  or None

    with _connect() as conn:
        patient_id = _get_or_create_patient(conn, patient)

        conn.execute(
            """INSERT INTO records
                   (id, patient_id, record_type, saved_at, report_path, sample_rows_json,
                    duration_options_json, drug, preparation, dose, dose_dt,
                    sample_collection_date, co_medications, scheme, trough,
                    prepared_by_id, checked_by_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET
                   patient_id             = EXCLUDED.patient_id,
                   record_type            = EXCLUDED.record_type,
                   saved_at               = EXCLUDED.saved_at,
                   report_path            = EXCLUDED.report_path,
                   sample_rows_json       = EXCLUDED.sample_rows_json,
                   duration_options_json  = EXCLUDED.duration_options_json,
                   drug                   = EXCLUDED.drug,
                   preparation            = EXCLUDED.preparation,
                   dose                   = EXCLUDED.dose,
                   dose_dt                = EXCLUDED.dose_dt,
                   sample_collection_date = EXCLUDED.sample_collection_date,
                   co_medications         = EXCLUDED.co_medications,
                   scheme                 = EXCLUDED.scheme,
                   trough                 = EXCLUDED.trough,
                   prepared_by_id         = EXCLUDED.prepared_by_id,
                   checked_by_id          = EXCLUDED.checked_by_id""",
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
                prepared_by_id,
                checked_by_id,
            )
        )

        conn.execute("DELETE FROM sample_points WHERE record_id = %s", (snapshot['id'],))
        for i, (t, c) in enumerate(zip(snapshot.get('times', []), snapshot.get('concs', []))):
            conn.execute(
                """INSERT INTO sample_points (record_id, point_order, time_point, concentration)
                   VALUES (%s, %s, %s, %s)""",
                (snapshot['id'], i, t, c)
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
            conn.execute("DELETE FROM pk_results WHERE record_id = %s", (snapshot['id'],))


def delete_record(record_id: str):
    with _connect() as conn:
        conn.execute("DELETE FROM records WHERE id = %s", (record_id,))
        conn.execute("DELETE FROM drafts WHERE id = %s", (record_id,))


def load_all() -> tuple[list, list]:
    with _connect() as conn:
        records = conn.execute("""
            SELECT r.id, r.record_type, r.saved_at, r.report_path, r.sample_rows_json,
                   r.duration_options_json, r.drug, r.preparation, r.dose, r.dose_dt,
                   r.sample_collection_date, r.co_medications, r.scheme, r.trough,
                   r.prepared_by_id, r.checked_by_id,
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
            SELECT id, saved_at, report_path, sample_rows_json, duration_options_json,
                   times_json, concs_json, name, age, sex, invoice_date, invoice_number,
                   report_number, dept, diagnosis, tx_date, delivery_date,
                   drug, preparation, dose, dose_dt, sample_collection_date,
                   co_medications, scheme, trough, phone, prepared_by_id, checked_by_id
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
        if not row or not row['value']:
            return list(default_options)
        try:
            data = json.loads(row['value'])
            cleaned = []
            for item in data:
                try:
                    value = int(item)
                    if value > 0 and value not in cleaned:
                        cleaned.append(value)
                except Exception:
                    continue
            return cleaned or list(default_options)
        except Exception:
            return list(default_options)


def save_duration_options(options: list):
    with _connect() as conn:
        conn.execute(
            """INSERT INTO app_settings (key, value) VALUES ('duration_options', %s)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            (json.dumps(options),)
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


def load_doctors() -> list:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM doctors ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]


def get_doctor_by_id(doctor_id: int) -> dict | None:
    if not doctor_id:
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM doctors WHERE id = %s", (doctor_id,)).fetchone()
        return dict(row) if row else None


def is_doctor_phone_exists(phone: str, exclude_id: int = None) -> bool:
    if not phone:
        return False
    with _connect() as conn:
        if exclude_id:
            row = conn.execute(
                "SELECT 1 FROM doctors WHERE phone = %s AND id != %s", (phone, exclude_id)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM doctors WHERE phone = %s", (phone,)
            ).fetchone()
        return row is not None


def add_doctor(name: str, designation: str, signature_path: str = None,
               type: str = 'doctor', phone: str = None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO doctors (name, designation, signature_path, type, phone)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (name, designation, signature_path, type, phone)
        )
        return cur.fetchone()['id']


def update_doctor(doctor_id: int, name: str, designation: str,
                  signature_path: str = None, type: str = 'doctor', phone: str = None):
    with _connect() as conn:
        conn.execute(
            """UPDATE doctors
               SET name = %s, designation = %s, signature_path = %s, type = %s, phone = %s
               WHERE id = %s""",
            (name, designation, signature_path, type, phone, doctor_id)
        )


def delete_doctor(doctor_id: int):
    with _connect() as conn:
        conn.execute("DELETE FROM doctors WHERE id = %s", (doctor_id,))


def migrate_from_json(json_path: Path):
    if not json_path.exists():
        return
    try:
        data = json.loads(json_path.read_text())
        samples = data if isinstance(data, list) else data.get('samples', [])
        drafts  = [] if isinstance(data, list) else data.get('drafts', [])
        for snapshot in samples:
            try:
                save_record(snapshot, 'sample')
            except Exception:
                pass
        for snapshot in drafts:
            try:
                save_record(snapshot, 'draft')
            except Exception:
                pass
        json_path.rename(json_path.with_suffix('.json.bak'))
    except Exception:
        pass
