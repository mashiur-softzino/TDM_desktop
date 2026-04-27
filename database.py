"""
TDM Report — Database layer
SQLite backend replacing saved_patients.json
"""

import sqlite3
import json
import random
import string
from pathlib import Path
from datetime import datetime

DB_FILE = Path(__file__).resolve().with_name("tdm_report.db")
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

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
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
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                pid        TEXT UNIQUE,
                hosp_no    TEXT UNIQUE,
                name       TEXT,
                age        TEXT,
                sex        TEXT,
                weight     TEXT,
                ward       TEXT,
                dept       TEXT,
                diagnosis  TEXT,
                tx_date    TEXT
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
                trough                 TEXT
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
                weight                 TEXT,
                hosp_no                TEXT,
                ward                   TEXT,
                dept                   TEXT,
                diagnosis              TEXT,
                tx_date                TEXT,
                drug                   TEXT,
                preparation            TEXT,
                dose                   TEXT,
                dose_dt                TEXT,
                sample_collection_date TEXT,
                co_medications         TEXT,
                scheme                 INTEGER,
                trough                 TEXT
            );
        """)
        # Migrate: add pid column if missing (existing databases)
        if not _column_exists(conn, 'patients', 'pid'):
            conn.execute("ALTER TABLE patients ADD COLUMN pid TEXT")
            conn.commit()
        if not _column_exists(conn, 'records', 'report_path'):
            conn.execute("ALTER TABLE records ADD COLUMN report_path TEXT")
            conn.commit()
        if not _column_exists(conn, 'records', 'sample_rows_json'):
            conn.execute("ALTER TABLE records ADD COLUMN sample_rows_json TEXT")
            conn.commit()
        if not _column_exists(conn, 'records', 'duration_options_json'):
            conn.execute("ALTER TABLE records ADD COLUMN duration_options_json TEXT")
            conn.commit()
        if not _column_exists(conn, 'drafts', 'report_path'):
            conn.execute("ALTER TABLE drafts ADD COLUMN report_path TEXT")
            conn.commit()
        if not _column_exists(conn, 'drafts', 'sample_rows_json'):
            conn.execute("ALTER TABLE drafts ADD COLUMN sample_rows_json TEXT")
            conn.commit()
        if not _column_exists(conn, 'drafts', 'duration_options_json'):
            conn.execute("ALTER TABLE drafts ADD COLUMN duration_options_json TEXT")
            conn.commit()
        if not _column_exists(conn, 'drafts', 'times_json'):
            conn.execute("ALTER TABLE drafts ADD COLUMN times_json TEXT")
            conn.commit()
        if not _column_exists(conn, 'drafts', 'concs_json'):
            conn.execute("ALTER TABLE drafts ADD COLUMN concs_json TEXT")
            conn.commit()
        if not _column_exists(conn, 'pk_results', 'auc_lss'):
            conn.execute("ALTER TABLE pk_results ADD COLUMN auc_lss REAL")
            conn.commit()
        if not _column_exists(conn, 'pk_results', 'lss_equation'):
            conn.execute("ALTER TABLE pk_results ADD COLUMN lss_equation TEXT")
            conn.commit()
        _migrate_legacy_drafts(conn)
        for med in DEFAULT_MEDICATIONS_SEED:
            conn.execute("INSERT OR IGNORE INTO medications (name) VALUES (?)", (med,))
        conn.commit()


# ─────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────

def _generate_pid() -> str:
    date_str = datetime.now().strftime("%Y%m%d")
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"PID-{date_str}-{suffix}"


def _get_or_create_patient(conn: sqlite3.Connection, patient: dict) -> int:
    hosp_no = patient.get('hosp_id', '') or ''
    # Reuse existing patient if hospital number is real
    if hosp_no and hosp_no != 'N/A':
        row = conn.execute(
            "SELECT id FROM patients WHERE hosp_no = ?", (hosp_no,)
        ).fetchone()
        if row:
            return row['id']

    pid = _generate_pid()
    cursor = conn.execute(
        """INSERT INTO patients (pid, hosp_no, name, age, sex, weight, ward, dept, diagnosis, tx_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pid,
            hosp_no if hosp_no and hosp_no != 'N/A' else None,
            patient.get('name'),
            patient.get('age'),
            patient.get('sex'),
            patient.get('weight'),
            patient.get('ward'),
            patient.get('dept'),
            patient.get('diag'),
            patient.get('tx_date'),
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
        'weight':                 record['weight']                 or 'N/A',
        'hosp_id':                record['hosp_no']                or 'N/A',
        'pid':                    record['pid']                    or 'N/A',
        'ward':                   record['ward']                   or 'N/A',
        'dept':                   record['dept']                   or 'N/A',
        'drug':                   record['drug']                   or '',
        'preparation':            record['preparation']            or '',
        'dose':                   record['dose']                   or '',
        'dose_dt':                record['dose_dt']                or '',
        'sample_collection_date': record['sample_collection_date'] or '',
        'diag':                   record['diagnosis']              or 'N/A',
        'tx_date':                record['tx_date']                or '',
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
        'weight':                 row['weight']                 or 'N/A',
        'hosp_id':                row['hosp_no']                or 'N/A',
        'pid':                    'N/A',
        'ward':                   row['ward']                   or 'N/A',
        'dept':                   row['dept']                   or 'N/A',
        'drug':                   row['drug']                   or '',
        'preparation':            row['preparation']            or '',
        'dose':                   row['dose']                   or '',
        'dose_dt':                row['dose_dt']                or '',
        'sample_collection_date': row['sample_collection_date'] or '',
        'diag':                   row['diagnosis']              or 'N/A',
        'tx_date':                row['tx_date']                or '',
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
            name, age, sex, weight, hosp_no, ward, dept, diagnosis, tx_date,
            drug, preparation, dose, dose_dt, sample_collection_date, co_medications, scheme, trough)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            patient.get('weight'),
            patient.get('hosp_id'),
            patient.get('ward'),
            patient.get('dept'),
            patient.get('diag'),
            patient.get('tx_date'),
            patient.get('drug'),
            patient.get('preparation'),
            patient.get('dose'),
            patient.get('dose_dt'),
            patient.get('sample_collection_date'),
            patient.get('med'),
            snapshot.get('scheme'),
            snapshot.get('trough'),
        )
    )


def _migrate_legacy_drafts(conn: sqlite3.Connection):
    legacy_drafts = conn.execute("""
        SELECT r.id, r.saved_at, r.report_path, r.sample_rows_json, r.duration_options_json,
               r.drug, r.preparation, r.dose, r.dose_dt, r.sample_collection_date,
               r.co_medications, r.scheme, r.trough,
               p.hosp_no, p.name, p.age, p.sex, p.weight, p.ward, p.dept, p.diagnosis, p.tx_date
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
                'weight': row['weight'] or 'N/A',
                'hosp_id': row['hosp_no'] or 'N/A',
                'ward': row['ward'] or 'N/A',
                'dept': row['dept'] or 'N/A',
                'diag': row['diagnosis'] or 'N/A',
                'tx_date': row['tx_date'] or '',
                'drug': row['drug'] or '',
                'preparation': row['preparation'] or '',
                'dose': row['dose'] or '',
                'dose_dt': row['dose_dt'] or '',
                'sample_collection_date': row['sample_collection_date'] or '',
                'med': row['co_medications'] or 'N/A',
            },
            'scheme': row['scheme'] or 4,
            'duration_options': json.loads(row['duration_options_json']) if row['duration_options_json'] else [row['scheme'] or 4],
            'sample_rows': json.loads(row['sample_rows_json']) if row['sample_rows_json'] else [],
            'trough': row['trough'] or '',
            'times': times,
            'concs': concs,
        }
        _save_draft(conn, snapshot)
        conn.execute("DELETE FROM records WHERE id = ?", (row['id'],))


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
                sample_collection_date, co_medications, scheme, trough)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
    """Return (samples, drafts) as lists of snapshot dicts.

    Uses 3 bulk queries instead of 2N+1 per-record queries so performance
    stays constant regardless of how many records exist.
    """
    with _connect() as conn:
        records = conn.execute("""
            SELECT r.id, r.record_type, r.saved_at, r.report_path, r.sample_rows_json, r.duration_options_json, r.drug, r.preparation,
                   r.dose, r.dose_dt, r.sample_collection_date, r.co_medications,
                   r.scheme, r.trough,
                   p.pid, p.hosp_no, p.name, p.age, p.sex, p.weight,
                   p.ward, p.dept, p.diagnosis, p.tx_date
            FROM   records r
            LEFT JOIN patients p ON r.patient_id = p.id
            ORDER  BY r.saved_at ASC, r.id ASC
        """).fetchall()

        # Bulk-fetch sample points and pk results in one query each
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
            snapshot = _row_to_snapshot(
                rec,
                points_by_id.get(rec['id'], []),
                pk_by_id.get(rec['id']),
            )
            samples.append(snapshot)

        draft_rows = conn.execute("""
            SELECT id, saved_at, report_path, sample_rows_json, duration_options_json, times_json, concs_json,
                   name, age, sex, weight, hosp_no, ward, dept, diagnosis, tx_date,
                   drug, preparation, dose, dose_dt, sample_collection_date, co_medications, scheme, trough
            FROM drafts
            ORDER BY saved_at ASC, id ASC
        """).fetchall()
        drafts = [_draft_row_to_snapshot(row) for row in draft_rows]

        return samples, drafts


def load_duration_options(default_options: list[int]) -> list[int]:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = 'duration_options'").fetchone()
        if not row or not row['value']:
            return list(default_options)
        try:
            data = json.loads(row['value'])
        except Exception:
            return list(default_options)
        cleaned = []
        for item in data:
            try:
                value = int(item)
            except Exception:
                continue
            if value > 0 and value not in cleaned:
                cleaned.append(value)
        return cleaned or list(default_options)


def save_duration_options(options: list[int]):
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('duration_options', ?)",
            (json.dumps(options),)
        )


def load_medications() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT name FROM medications ORDER BY LOWER(name) ASC").fetchall()
        return [row["name"] for row in rows]


def add_medication(name: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("INSERT OR IGNORE INTO medications (name) VALUES (?)", (name,))
        return cur.rowcount > 0


def update_medication(old_name: str, new_name: str):
    with _connect() as conn:
        conn.execute("UPDATE medications SET name = ? WHERE name = ?", (new_name, old_name))


def delete_medication(name: str):
    with _connect() as conn:
        conn.execute("DELETE FROM medications WHERE name = ?", (name,))


# ─────────────────────────────────────────
# One-time JSON migration
# ─────────────────────────────────────────

def migrate_from_json(json_path: Path):
    """Import all records from saved_patients.json then rename it as .bak."""
    if not json_path.exists():
        return
    try:
        data = json.loads(json_path.read_text())
    except Exception:
        return

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
