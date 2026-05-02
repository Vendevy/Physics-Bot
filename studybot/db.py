import sqlite3
from contextlib import contextmanager
from .config import DB_PATH, DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    board TEXT NOT NULL,
    spec_pdf TEXT NOT NULL,
    spec_file_id TEXT
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    parent_id INTEGER REFERENCES topics(id),
    depth INTEGER NOT NULL,
    content TEXT,
    UNIQUE(subject_id, code)
);
CREATE INDEX IF NOT EXISTS idx_topics_subject ON topics(subject_id);
CREATE INDEX IF NOT EXISTS idx_topics_parent ON topics(parent_id);

CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    label TEXT NOT NULL,
    qp_path TEXT NOT NULL,
    ms_path TEXT,
    qp_file_id TEXT,
    ms_file_id TEXT,
    extracted_at TEXT,
    UNIQUE(subject_id, label)
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    paper_id INTEGER REFERENCES papers(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    source TEXT NOT NULL,           -- 'past_paper' or 'generated'
    qnum TEXT,                       -- e.g. '3(b)(ii)'
    text TEXT NOT NULL,
    marks INTEGER NOT NULL,
    markscheme TEXT,
    figure TEXT,                     -- optional Chart.js JSON for generated questions
    scenario TEXT,                   -- short kebab-case tag describing the physical scenario (generated questions)
    flagged INTEGER NOT NULL DEFAULT 0,
    flag_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject_id);
CREATE INDEX IF NOT EXISTS idx_questions_paper ON questions(paper_id);

CREATE TABLE IF NOT EXISTS question_topics (
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_qt_topic ON question_topics(topic_id);

CREATE TABLE IF NOT EXISTS mastery (
    topic_id INTEGER PRIMARY KEY REFERENCES topics(id) ON DELETE CASCADE,
    score REAL NOT NULL DEFAULT 0.0,        -- 0..1
    ease REAL NOT NULL DEFAULT 2.5,         -- SM-2 ease factor
    interval_days INTEGER NOT NULL DEFAULT 0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    last_reviewed TEXT,
    next_review TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    answered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_answer TEXT NOT NULL,
    marks_awarded INTEGER NOT NULL,
    total_marks INTEGER NOT NULL,
    sm2_grade INTEGER NOT NULL,             -- 0..5
    feedback TEXT,
    time_spent_seconds INTEGER              -- wall-clock from question shown to submit
);
CREATE INDEX IF NOT EXISTS idx_attempts_question ON attempts(question_id);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    mode TEXT NOT NULL DEFAULT 'daily',     -- 'daily' or 'mock_paper'
    paper_id INTEGER REFERENCES papers(id)  -- only set for mock_paper sessions
);

CREATE TABLE IF NOT EXISTS session_questions (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    kind TEXT NOT NULL,                     -- 'new' or 'recall'
    position INTEGER NOT NULL,
    attempt_id INTEGER REFERENCES attempts(id),
    consolidation TEXT,
    PRIMARY KEY (session_id, position)
);

CREATE TABLE IF NOT EXISTS files_cache (
    path TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
    migrate()


def migrate() -> None:
    """Idempotent column additions for already-created databases."""
    with connect() as conn:
        sq_cols = {r["name"] for r in conn.execute("PRAGMA table_info(session_questions)").fetchall()}
        if "consolidation" not in sq_cols:
            conn.execute("ALTER TABLE session_questions ADD COLUMN consolidation TEXT")
        q_cols = {r["name"] for r in conn.execute("PRAGMA table_info(questions)").fetchall()}
        if "flagged" not in q_cols:
            conn.execute("ALTER TABLE questions ADD COLUMN flagged INTEGER NOT NULL DEFAULT 0")
        if "flag_reason" not in q_cols:
            conn.execute("ALTER TABLE questions ADD COLUMN flag_reason TEXT")
        if "figure" not in q_cols:
            conn.execute("ALTER TABLE questions ADD COLUMN figure TEXT")
        if "scenario" not in q_cols:
            conn.execute("ALTER TABLE questions ADD COLUMN scenario TEXT")
        a_cols = {r["name"] for r in conn.execute("PRAGMA table_info(attempts)").fetchall()}
        if "time_spent_seconds" not in a_cols:
            conn.execute("ALTER TABLE attempts ADD COLUMN time_spent_seconds INTEGER")
        if "error_tags" not in a_cols:
            conn.execute("ALTER TABLE attempts ADD COLUMN error_tags TEXT")
        s_cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        if "mode" not in s_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'daily'")
        if "paper_id" not in s_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN paper_id INTEGER REFERENCES papers(id)")
        conn.commit()


@contextmanager
def tx():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_subject(conn: sqlite3.Connection, name: str):
    return conn.execute("SELECT * FROM subjects WHERE name = ?", (name,)).fetchone()


def upsert_subject(conn: sqlite3.Connection, name: str, board: str, spec_pdf: str) -> int:
    cur = conn.execute(
        "INSERT INTO subjects(name, board, spec_pdf) VALUES(?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET board=excluded.board, spec_pdf=excluded.spec_pdf "
        "RETURNING id",
        (name, board, spec_pdf),
    )
    return cur.fetchone()["id"]
