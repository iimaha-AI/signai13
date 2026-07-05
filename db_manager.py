"""
SignAI Database Manager (PostgreSQL edition).

Drop-in replacement for the original SQLite-based db_manager.py.
The public function signatures and return types are kept identical so
app.py does not need to be modified.

Connection string is read from cfg.DATABASE_URL (set via the
DATABASE_URL environment variable, e.g. a Neon / Supabase / Render
Postgres connection string).
"""

import logging
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# Module-level state, populated by init_db_config()
_db_url: str | None = None


def init_db_config(cfg) -> None:
    """Store the DATABASE_URL from the Flask config object."""
    global _db_url
    _db_url = getattr(cfg, "DATABASE_URL", None) or None
    if not _db_url:
        logger.warning("DATABASE_URL is not set — db_manager will not function.")
    else:
        # Mask the password when logging.
        safe = _db_url
        try:
            from urllib.parse import urlparse, urlunparse
            p = urlparse(_db_url)
            if p.password:
                masked = p._replace(
                    netloc=f"{p.username}:***@{p.hostname}"
                    + (f":{p.port}" if p.port else "")
                )
                safe = urlunparse(masked)
        except Exception:
            pass
        logger.info("Database configured: %s", safe)


@contextmanager
def _conn():
    """Yield a psycopg2 connection with dict-style rows; commit on success."""
    conn = None
    if not _db_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    try:
        conn = psycopg2.connect(_db_url, cursor_factory=RealDictCursor)
        conn.autocommit = False
        yield conn
        conn.commit()
    except psycopg2.Error:
        if conn:
            conn.rollback()
        logger.error("Database error:\n%s", traceback.format_exc())
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Schema initialization
# ─────────────────────────────────────────────────────────────────────────────

def init_db() -> bool:
    """Create tables if they do not exist (idempotent)."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                # ── users table ──────────────────────────────────────────────
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id                    SERIAL PRIMARY KEY,
                        fullname              VARCHAR(120) NOT NULL,
                        email                 VARCHAR(255) NOT NULL UNIQUE,
                        password_hash         VARCHAR(256) NOT NULL,
                        is_admin              INTEGER      NOT NULL DEFAULT 0,
                        confidence_threshold  REAL         NOT NULL DEFAULT 0.70,
                        created_at            TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_login            TIMESTAMP    NULL
                    )
                """)

                # ── predictions table ────────────────────────────────────────
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS predictions (
                        id                   SERIAL PRIMARY KEY,
                        user_id              INTEGER       NULL,
                        session_id           VARCHAR(64)   NOT NULL,
                        letter               CHAR(1)       NOT NULL,
                        confidence           REAL          NOT NULL,
                        top5_json            TEXT          NULL,
                        letter_scores_json   TEXT          NULL,
                        created_at           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)

                # ── sessions (sentence builder) table ────────────────────────
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id          SERIAL PRIMARY KEY,
                        user_id     INTEGER   NOT NULL,
                        sentence    TEXT      NOT NULL,
                        created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)

                # ── indexes ─────────────────────────────────────────────────
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_predictions_user_created
                    ON predictions (user_id, created_at)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sessions_user_updated
                    ON sessions (user_id, updated_at DESC)
                """)

                # ── idempotent migrations (add columns if missing) ──────────
                cur.execute("""
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS confidence_threshold
                    REAL NOT NULL DEFAULT 0.70
                """)

        logger.info("Database schema initialized successfully.")
        return True
    except psycopg2.Error:
        logger.error("Failed to initialize database schema:\n%s", traceback.format_exc())
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Users CRUD
# ─────────────────────────────────────────────────────────────────────────────

def create_user(fullname: str, email: str, password_hash: str) -> int | None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO users (fullname, email, password_hash)
                       VALUES (%s, %s, %s) RETURNING id""",
                    (fullname.strip(), email.strip().lower(), password_hash),
                )
                row = cur.fetchone()
                return int(row["id"]) if row else None
    except psycopg2.Error:
        logger.error("create_user failed:\n%s", traceback.format_exc())
        return None


def get_user_by_email(email: str) -> dict | None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM users WHERE email = %s LIMIT 1",
                    (email.strip().lower(),),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except psycopg2.Error:
        logger.error("get_user_by_email failed:\n%s", traceback.format_exc())
        return None


def get_user_by_id(user_id: int) -> dict | None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM users WHERE id = %s LIMIT 1",
                    (user_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except psycopg2.Error:
        logger.error("get_user_by_id failed:\n%s", traceback.format_exc())
        return None


def update_last_login(user_id: int) -> None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET last_login = %s WHERE id = %s",
                    (datetime.now(timezone.utc), user_id),
                )
    except psycopg2.Error:
        logger.error("update_last_login failed:\n%s", traceback.format_exc())


def update_user_name(user_id: int, fullname: str) -> bool:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET fullname = %s WHERE id = %s",
                    (fullname.strip(), user_id),
                )
                return True
    except psycopg2.Error:
        logger.error("update_user_name failed:\n%s", traceback.format_exc())
        return False


def update_user_password(user_id: int, new_hash: str) -> bool:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (new_hash, user_id),
                )
                return True
    except psycopg2.Error:
        logger.error("update_user_password failed:\n%s", traceback.format_exc())
        return False


def update_confidence_threshold(user_id: int, threshold: float) -> bool:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET confidence_threshold = %s WHERE id = %s",
                    (float(threshold), user_id),
                )
                return True
    except psycopg2.Error:
        logger.error("update_confidence_threshold failed:\n%s", traceback.format_exc())
        return False


def delete_user(user_id: int) -> bool:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                return True
    except psycopg2.Error:
        logger.error("delete_user failed:\n%s", traceback.format_exc())
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Predictions
# ─────────────────────────────────────────────────────────────────────────────

def save_prediction(user_id, session_id: str, letter: str, confidence: float,
                    top5_json: str, letter_scores_json: str = None) -> int | None:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO predictions
                       (user_id, session_id, letter, confidence, top5_json, letter_scores_json)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (user_id, session_id, letter, confidence, top5_json, letter_scores_json),
                )
                row = cur.fetchone()
                return int(row["id"]) if row else None
    except psycopg2.Error:
        logger.error("save_prediction failed:\n%s", traceback.format_exc())
        return None


def get_history(user_id: int, page: int = 1, per_page: int = 20) -> dict:
    offset = (page - 1) * per_page
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total FROM predictions WHERE user_id = %s",
                    (user_id,),
                )
                total = cur.fetchone()["total"]

                cur.execute(
                    """SELECT id, letter, confidence, top5_json, created_at
                       FROM predictions
                       WHERE user_id = %s
                       ORDER BY created_at DESC
                       LIMIT %s OFFSET %s""",
                    (user_id, per_page, offset),
                )
                rows = [dict(r) for r in cur.fetchall()]

                # Convert datetimes to ISO strings for JSON friendliness
                for row in rows:
                    ca = row.get("created_at")
                    if isinstance(ca, datetime):
                        row["created_at"] = ca.isoformat()

        return {
            "rows": rows,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, -(-total // per_page)) if total else 1,
        }
    except psycopg2.Error:
        logger.error("get_history failed:\n%s", traceback.format_exc())
        return {"rows": [], "total": 0, "page": page, "per_page": per_page, "pages": 1}


def delete_all_predictions(user_id: int) -> bool:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM predictions WHERE user_id = %s", (user_id,))
                return True
    except psycopg2.Error:
        logger.error("delete_all_predictions failed:\n%s", traceback.format_exc())
        return False


def delete_predictions_by_ids(user_id: int, ids: list) -> bool:
    if not ids:
        return True
    try:
        # psycopg2 handles list expansion via ANY(%s)
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM predictions WHERE user_id = %s AND id = ANY(%s)",
                    (user_id, list(ids)),
                )
                return True
    except psycopg2.Error:
        logger.error("delete_predictions_by_ids failed:\n%s", traceback.format_exc())
        return False


def get_user_stats(user_id: int, date_range: str = "all") -> dict:
    """Aggregate stats for the user, mirroring the original SQLite version."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                # Time filter clause (PostgreSQL interval syntax)
                time_filter = ""
                if date_range == "1d":
                    time_filter = " AND created_at >= NOW() - INTERVAL '1 day'"
                elif date_range == "7d":
                    time_filter = " AND created_at >= NOW() - INTERVAL '7 days'"
                elif date_range == "30d":
                    time_filter = " AND created_at >= NOW() - INTERVAL '30 days'"

                cur.execute(
                    f"""SELECT COUNT(*)                                  AS total,
                               COALESCE(AVG(confidence), 0)              AS avg_confidence,
                               COUNT(DISTINCT letter)                    AS unique_letters,
                               COALESCE(MAX(confidence), 0)              AS best_confidence
                        FROM predictions
                        WHERE user_id = %s{time_filter}""",
                    (user_id,),
                )
                row = cur.fetchone()

                cur.execute(
                    f"""SELECT letter, COUNT(*) AS cnt
                        FROM predictions
                        WHERE user_id = %s{time_filter}
                        GROUP BY letter
                        ORDER BY cnt DESC LIMIT 1""",
                    (user_id,),
                )
                top_row = cur.fetchone()

                cur.execute(
                    f"""SELECT letter, COUNT(*) AS cnt
                        FROM predictions
                        WHERE user_id = %s{time_filter}
                        GROUP BY letter
                        ORDER BY cnt DESC""",
                    (user_id,),
                )
                freq_rows = cur.fetchall()

                cur.execute(
                    f"""SELECT created_at::date AS day, COUNT(*) AS cnt
                        FROM predictions
                        WHERE user_id = %s{time_filter}
                        GROUP BY created_at::date
                        ORDER BY day DESC""",
                    (user_id,),
                )
                daily_rows = [dict(r) for r in cur.fetchall()]
                for r in daily_rows:
                    if r.get("day") is not None:
                        r["day"] = r["day"].isoformat()

                cur.execute(
                    f"""SELECT created_at::date AS day, AVG(confidence) AS avg_conf
                        FROM predictions
                        WHERE user_id = %s{time_filter}
                        GROUP BY created_at::date
                        ORDER BY day ASC""",
                    (user_id,),
                )
                conf_over_time = [dict(r) for r in cur.fetchall()]
                for r in conf_over_time:
                    if r.get("day") is not None:
                        r["day"] = r["day"].isoformat()

                cur.execute(
                    f"""SELECT EXTRACT(HOUR FROM created_at)::int AS hr,
                               COUNT(*) AS cnt
                        FROM predictions
                        WHERE user_id = %s{time_filter}
                        GROUP BY EXTRACT(HOUR FROM created_at)
                        ORDER BY hr ASC""",
                    (user_id,),
                )
                hourly = [dict(r) for r in cur.fetchall()]

                cur.execute(
                    f"""SELECT letter, confidence, created_at
                        FROM predictions
                        WHERE user_id = %s{time_filter}
                        ORDER BY confidence DESC LIMIT 1""",
                    (user_id,),
                )
                best_row = cur.fetchone()
                if best_row:
                    best_row = dict(best_row)
                    if isinstance(best_row.get("created_at"), datetime):
                        best_row["created_at"] = best_row["created_at"].isoformat()

        total = int(row["total"] or 0)
        avg_conf = float(row["avg_confidence"] or 0.0)

        return {
            "total_predictions": total,
            "avg_confidence": round(avg_conf, 2),
            "unique_letters": int(row["unique_letters"] or 0),
            "most_predicted": top_row["letter"] if top_row else None,
            "best_confidence": float(row["best_confidence"] or 0.0),
            "letter_frequency": {r["letter"]: r["cnt"] for r in freq_rows},
            "daily_counts": daily_rows,
            "confidence_over_time": conf_over_time,
            "hourly_distribution": hourly,
            "personal_best": best_row,
        }
    except psycopg2.Error:
        logger.error("get_user_stats failed:\n%s", traceback.format_exc())
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Word / sentence sessions
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_word_session(user_id: int) -> dict:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM sessions
                       WHERE user_id = %s
                       ORDER BY updated_at DESC LIMIT 1""",
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        "INSERT INTO sessions (user_id, sentence) VALUES (%s, %s) RETURNING *",
                        (user_id, ""),
                    )
                    return dict(cur.fetchone())
                return dict(row)
    except psycopg2.Error:
        logger.error("get_or_create_word_session failed:\n%s", traceback.format_exc())
        return {"id": None, "user_id": user_id, "sentence": ""}


def update_word_session(session_id: int, sentence: str) -> bool:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                # PostgreSQL doesn't have ON UPDATE CURRENT_TIMESTAMP;
                # update updated_at manually.
                now = datetime.now(timezone.utc)
                cur.execute(
                    "UPDATE sessions SET sentence = %s, updated_at = %s WHERE id = %s",
                    (sentence, now, session_id),
                )
                return True
    except psycopg2.Error:
        logger.error("update_word_session failed:\n%s", traceback.format_exc())
        return False


def get_sentence_history(user_id: int, limit: int = 20) -> list:
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT sentence, created_at, updated_at
                       FROM sessions
                       WHERE user_id = %s AND sentence <> ''
                       ORDER BY updated_at DESC LIMIT %s""",
                    (user_id, limit),
                )
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    for k in ("created_at", "updated_at"):
                        v = r.get(k)
                        if isinstance(v, datetime):
                            r[k] = v.isoformat()
                return rows
    except psycopg2.Error:
        logger.error("get_sentence_history failed:\n%s", traceback.format_exc())
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Global admin stats
# ─────────────────────────────────────────────────────────────────────────────

def get_model_stats_global() -> dict:
    """Aggregate stats across all users for admin model analytics."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS total FROM predictions")
                total = cur.fetchone()["total"]
                cur.execute(
                    """SELECT letter, COUNT(*) AS cnt FROM predictions
                       GROUP BY letter ORDER BY cnt DESC LIMIT 5"""
                )
                top5 = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """SELECT letter, COUNT(*) AS cnt FROM predictions
                       GROUP BY letter ORDER BY cnt ASC LIMIT 5"""
                )
                bottom5 = [dict(r) for r in cur.fetchall()]
        return {"total_inferences": total, "top5_letters": top5, "bottom5_letters": bottom5}
    except psycopg2.Error:
        logger.error("get_model_stats_global failed:\n%s", traceback.format_exc())
        return {}
