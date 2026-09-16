"""Persistência da Feira Tech em PostgreSQL (pensado para o Postgres gratuito do Render).

Mantém a mesma interface pública do antigo json_store.py (mesmas funções e
formatos de retorno), então app.py só precisa trocar o import.
"""

import csv
import hashlib
import hmac
import io
import os
import secrets
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.errors
import psycopg2.extras

VALID_COURSES = {"python", "web", "audio", "outro"}

DATABASE_URL = os.environ["DATABASE_URL"]
# O Render entrega a URL como postgres://; psycopg2 aceita postgresql://.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


@contextmanager
def _conn():
    connection = psycopg2.connect(DATABASE_URL, sslmode="require")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _dict_cursor(connection):
    return connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    with _conn() as connection:
        with connection.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS stands (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    name_normalized TEXT NOT NULL UNIQUE,
                    course TEXT NOT NULL,
                    code_salt TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS visitas (
                    id TEXT PRIMARY KEY,
                    stand_id TEXT NOT NULL REFERENCES stands(id),
                    stand_nome TEXT NOT NULL,
                    curso TEXT NOT NULL,
                    visitor_hash TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL,
                    finished_at TIMESTAMPTZ,
                    duration_seconds INT,
                    stars INT
                );
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uniq_visita_finalizada
                ON visitas (stand_id, visitor_hash)
                WHERE finished_at IS NOT NULL;
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS engajamentos (
                    id TEXT PRIMARY KEY,
                    stand_id TEXT NOT NULL REFERENCES stands(id),
                    stand_nome TEXT NOT NULL,
                    visitor_hash TEXT NOT NULL,
                    type TEXT NOT NULL,
                    message TEXT,
                    stars INT,
                    status TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    moderated_at TIMESTAMPTZ
                );
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uniq_apoio_por_visitante
                ON engajamentos (stand_id, visitor_hash)
                WHERE type = 'support';
                """
            )


init_db()


def _normalize_name(name):
    return " ".join(name.split()).casefold()


def _hash(value, salt):
    return hashlib.pbkdf2_hmac("sha256", value.encode(), salt.encode(), 120_000).hex()


def _public_stand(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "course": row["course"],
        "created_at": row["created_at"].isoformat(timespec="seconds"),
    }


def _find_stand(cur, stand_id):
    cur.execute("SELECT * FROM stands WHERE id = %s", (stand_id,))
    return cur.fetchone()


def list_public_stands():
    with _conn() as connection:
        with _dict_cursor(connection) as cur:
            cur.execute("SELECT * FROM stands ORDER BY created_at")
            return [_public_stand(row) for row in cur.fetchall()]


def get_public_stand(stand_id):
    with _conn() as connection:
        with _dict_cursor(connection) as cur:
            return _public_stand(_find_stand(cur, stand_id))


def create_stand(name, course):
    access_code = "".join(secrets.choice("23456789") for _ in range(6))
    salt = secrets.token_hex(16)
    stand_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    try:
        with _conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stands (id, name, name_normalized, course, code_salt, code_hash, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (stand_id, name, _normalize_name(name), course, salt, _hash(access_code, salt), now),
                )
    except psycopg2.errors.UniqueViolation:
        return None, None, "duplicate"
    stand = {"id": stand_id, "name": name, "course": course, "created_at": now.isoformat(timespec="seconds")}
    return stand, access_code, None


def verify_code(stand_row, access_code):
    if not stand_row or not access_code:
        return False
    expected = _hash(access_code, stand_row["code_salt"])
    return hmac.compare_digest(expected, stand_row["code_hash"])


def authenticate_stand(stand_id, access_code):
    with _conn() as connection:
        with _dict_cursor(connection) as cur:
            row = _find_stand(cur, stand_id)
            return _public_stand(row) if verify_code(row, access_code) else None


def start_visit(stand_id, visitor_key):
    visitor_hash = hashlib.sha256(visitor_key.encode()).hexdigest()
    with _conn() as connection:
        with _dict_cursor(connection) as cur:
            stand = _find_stand(cur, stand_id)
            if not stand:
                return None, "not_found"

            cur.execute(
                """
                SELECT id FROM visitas
                WHERE stand_id = %s AND visitor_hash = %s AND finished_at IS NOT NULL
                LIMIT 1
                """,
                (stand_id, visitor_hash),
            )
            if cur.fetchone():
                return None, "duplicate"

            cur.execute(
                """
                SELECT id FROM visitas
                WHERE stand_id = %s AND visitor_hash = %s AND finished_at IS NULL
                LIMIT 1
                """,
                (stand_id, visitor_hash),
            )
            active = cur.fetchone()
            if active:
                return active["id"], None

            visit_id = uuid.uuid4().hex
            cur.execute(
                """
                INSERT INTO visitas (id, stand_id, stand_nome, curso, visitor_hash, started_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (visit_id, stand_id, stand["name"], stand["course"], visitor_hash, datetime.now(timezone.utc)),
            )
            return visit_id, None


def finish_visit(visit_id, stand_id, visitor_key, stars):
    visitor_hash = hashlib.sha256(visitor_key.encode()).hexdigest()
    try:
        with _conn() as connection:
            with _dict_cursor(connection) as cur:
                cur.execute(
                    """
                    SELECT * FROM visitas
                    WHERE id = %s AND stand_id = %s AND visitor_hash = %s
                    """,
                    (visit_id, stand_id, visitor_hash),
                )
                visit = cur.fetchone()
                if not visit:
                    return None, "not_found"
                if visit["finished_at"]:
                    return None, "duplicate"

                finished_at = datetime.now(timezone.utc)
                duration = max(1, min(int((finished_at - visit["started_at"]).total_seconds()), 43_200))
                cur.execute(
                    """
                    UPDATE visitas SET finished_at = %s, duration_seconds = %s, stars = %s
                    WHERE id = %s
                    """,
                    (finished_at, duration, stars, visit_id),
                )
    except psycopg2.errors.UniqueViolation:
        return None, "duplicate"

    visit["finished_at"] = finished_at
    visit["duration_seconds"] = duration
    visit["stars"] = stars
    return dict(visit), None


def _last_finished_visit(cur, stand_id, visitor_hash):
    cur.execute(
        """
        SELECT stars FROM visitas
        WHERE stand_id = %s AND visitor_hash = %s AND finished_at IS NOT NULL
        ORDER BY finished_at DESC LIMIT 1
        """,
        (stand_id, visitor_hash),
    )
    return cur.fetchone()


def register_share(stand_id, visitor_key):
    visitor_hash = hashlib.sha256(visitor_key.encode()).hexdigest()
    with _conn() as connection:
        with _dict_cursor(connection) as cur:
            stand = _find_stand(cur, stand_id)
            if not stand or not _last_finished_visit(cur, stand_id, visitor_hash):
                return False
            cur.execute(
                """
                INSERT INTO engajamentos (id, stand_id, stand_nome, visitor_hash, type, created_at)
                VALUES (%s, %s, %s, %s, 'share', %s)
                """,
                (uuid.uuid4().hex, stand_id, stand["name"], visitor_hash, datetime.now(timezone.utc)),
            )
            return True


def create_support(stand_id, visitor_key, message):
    visitor_hash = hashlib.sha256(visitor_key.encode()).hexdigest()
    support_id = uuid.uuid4().hex
    try:
        with _conn() as connection:
            with _dict_cursor(connection) as cur:
                stand = _find_stand(cur, stand_id)
                visit = _last_finished_visit(cur, stand_id, visitor_hash) if stand else None
                if not stand or not visit:
                    return None, "visit_required"
                cur.execute(
                    """
                    INSERT INTO engajamentos
                        (id, stand_id, stand_nome, visitor_hash, type, message, stars, status, created_at)
                    VALUES (%s, %s, %s, %s, 'support', %s, %s, 'pending', %s)
                    """,
                    (support_id, stand_id, stand["name"], visitor_hash, message, visit["stars"], datetime.now(timezone.utc)),
                )
    except psycopg2.errors.UniqueViolation:
        return None, "duplicate"
    return {"id": support_id, "status": "pending"}, None


def public_wall(limit=24):
    with _conn() as connection:
        with _dict_cursor(connection) as cur:
            cur.execute(
                """
                SELECT id, stand_id, stand_nome AS stand_name, message, stars, created_at
                FROM engajamentos
                WHERE type = 'support' AND status = 'approved'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = [dict(row) for row in cur.fetchall()]
            for row in rows:
                row["created_at"] = row["created_at"].isoformat(timespec="seconds")
            return rows


def moderate_support(stand_id, engagement_id, access_code, action):
    with _conn() as connection:
        with _dict_cursor(connection) as cur:
            stand = _find_stand(cur, stand_id)
            if not verify_code(stand, access_code):
                return None, "unauthorized"
            cur.execute(
                "SELECT id FROM engajamentos WHERE id = %s AND stand_id = %s AND type = 'support'",
                (engagement_id, stand_id),
            )
            if not cur.fetchone():
                return None, "not_found"
            status = "approved" if action == "approve" else "rejected"
            cur.execute(
                "UPDATE engajamentos SET status = %s, moderated_at = %s WHERE id = %s",
                (status, datetime.now(timezone.utc), engagement_id),
            )
            return {"id": engagement_id, "status": status}, None


def dashboard(stand_id, access_code):
    with _conn() as connection:
        with _dict_cursor(connection) as cur:
            stand = _find_stand(cur, stand_id)
            if not verify_code(stand, access_code):
                return None

            cur.execute(
                """
                SELECT duration_seconds, stars, finished_at FROM visitas
                WHERE stand_id = %s AND finished_at IS NOT NULL
                ORDER BY finished_at
                """,
                (stand_id,),
            )
            visits = cur.fetchall()
            durations = [v["duration_seconds"] for v in visits]
            ratings = [v["stars"] for v in visits]
            distribution = {str(star): ratings.count(star) for star in range(1, 6)}
            recent = [
                {
                    "finished_at": v["finished_at"].isoformat(timespec="seconds"),
                    "duration_seconds": v["duration_seconds"],
                    "stars": v["stars"],
                }
                for v in list(reversed(visits))[:12]
            ]

            cur.execute("SELECT type, status FROM engajamentos WHERE stand_id = %s", (stand_id,))
            engagements = cur.fetchall()

            cur.execute(
                """
                SELECT id, message, stars, created_at FROM engajamentos
                WHERE stand_id = %s AND type = 'support' AND status = 'pending'
                ORDER BY created_at DESC
                """,
                (stand_id,),
            )
            pending = [dict(row) for row in cur.fetchall()]
            for row in pending:
                row["created_at"] = row["created_at"].isoformat(timespec="seconds")

            return {
                "stand": _public_stand(stand),
                "visitors": len(visits),
                "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
                "average_duration_seconds": round(sum(durations) / len(durations)) if durations else 0,
                "total_duration_seconds": sum(durations),
                "distribution": distribution,
                "recent_visits": recent,
                "shares": sum(1 for item in engagements if item["type"] == "share"),
                "approved_supports": sum(
                    1 for item in engagements if item["type"] == "support" and item["status"] == "approved"
                ),
                "pending_supports": pending,
            }


def export_visits_csv(stand_id, access_code):
    with _conn() as connection:
        with _dict_cursor(connection) as cur:
            stand = _find_stand(cur, stand_id)
            if not verify_code(stand, access_code):
                return None
            cur.execute(
                """
                SELECT finished_at, stars, duration_seconds FROM visitas
                WHERE stand_id = %s AND finished_at IS NOT NULL
                ORDER BY finished_at
                """,
                (stand_id,),
            )
            visits = cur.fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["data_hora", "estrelas", "duracao_segundos"])
    for visit in visits:
        writer.writerow([visit["finished_at"].isoformat(timespec="seconds"), visit["stars"], visit["duration_seconds"]])
    return buffer.getvalue().encode("utf-8-sig")
