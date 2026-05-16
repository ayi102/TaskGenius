import os
import re
import socket
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime

from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "taskgenius.db")

CATEGORIES = ("baby", "kitchen", "cleaning", "therapy", "other")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

app = Flask(__name__)


def get_port():
    return int(os.environ.get("PORT", "5000"))


def get_lan_ip():
    # Prefer wlan0 (the Pi's wifi) so the readout matches what the user expects.
    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "wlan0"],
            text=True, stderr=subprocess.DEVNULL, timeout=2,
        )
        for tok in out.split():
            if "/" in tok and tok.split("/")[0].count(".") == 3:
                return tok.split("/")[0]
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    # Fallback: ask the kernel which local IP would route to the internet.
    # Works on the laptop and on a Pi connected via ethernet.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        g._db = db
    return db


@app.teardown_appcontext
def close_db(_exc):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


def init_db():
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT    NOT NULL,
                notes           TEXT    NOT NULL DEFAULT '',
                category        TEXT    NOT NULL,
                scheduled_time  TEXT,
                position        INTEGER NOT NULL DEFAULT 0,
                created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_time ON tasks(scheduled_time);
            CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category);
            """
        )
        cols = {r[1] for r in db.execute("PRAGMA table_info(tasks)").fetchall()}
        if "days_of_week" not in cols:
            db.execute("ALTER TABLE tasks ADD COLUMN days_of_week TEXT")
        db.commit()


def parse_form(form):
    title = (form.get("title") or "").strip()
    notes = (form.get("notes") or "").strip()
    category = (form.get("category") or "").strip().lower()
    scheduled_time = (form.get("scheduled_time") or "").strip()
    picked = [d for d in form.getlist("days") if d in DAYS]
    # NULL = every day; only store a subset when the user actually narrowed it.
    days_of_week = ",".join(picked) if picked and len(picked) < len(DAYS) else None

    errors = []
    if not title:
        errors.append("Title is required.")
    if category not in CATEGORIES:
        errors.append("Pick a valid category.")
    if scheduled_time and not TIME_RE.match(scheduled_time):
        errors.append("Time must be HH:MM (24-hour) or blank.")

    return {
        "title": title,
        "notes": notes,
        "category": category,
        "scheduled_time": scheduled_time or None,
        "days_of_week": days_of_week,
    }, errors


def fetch_tasks():
    rows = get_db().execute(
        """
        SELECT id, title, notes, category, scheduled_time, position, days_of_week
        FROM tasks
        ORDER BY
            CASE WHEN scheduled_time IS NULL THEN 1 ELSE 0 END,
            scheduled_time ASC,
            category ASC,
            position ASC,
            id ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]


@app.route("/")
def display():
    return render_template(
        "display.html",
        categories=CATEGORIES,
        lan_ip=get_lan_ip(),
        port=get_port(),
    )


@app.route("/admin")
def admin():
    tasks = fetch_tasks()
    edit_id = request.args.get("edit", type=int)
    return render_template(
        "admin.html",
        tasks=tasks,
        categories=CATEGORIES,
        days=DAYS,
        form={},
        errors=[],
        editing_id=edit_id,
    )


@app.route("/tasks", methods=["POST"])
def create_task():
    data, errors = parse_form(request.form)
    if errors:
        tasks = fetch_tasks()
        return render_template(
            "admin.html",
            tasks=tasks,
            categories=CATEGORIES,
            days=DAYS,
            form=data,
            errors=errors,
        ), 400

    db = get_db()
    db.execute(
        "INSERT INTO tasks (title, notes, category, scheduled_time, days_of_week) VALUES (?, ?, ?, ?, ?)",
        (data["title"], data["notes"], data["category"], data["scheduled_time"], data["days_of_week"]),
    )
    db.commit()
    return redirect(url_for("admin"))


@app.route("/tasks/<int:task_id>/edit", methods=["POST"])
def edit_task(task_id):
    data, errors = parse_form(request.form)
    if errors:
        tasks = fetch_tasks()
        return render_template(
            "admin.html",
            tasks=tasks,
            categories=CATEGORIES,
            days=DAYS,
            form={**data, "id": task_id},
            errors=errors,
            editing_id=task_id,
        ), 400

    db = get_db()
    cur = db.execute(
        """
        UPDATE tasks
        SET title = ?, notes = ?, category = ?, scheduled_time = ?, days_of_week = ?
        WHERE id = ?
        """,
        (data["title"], data["notes"], data["category"], data["scheduled_time"], data["days_of_week"], task_id),
    )
    if cur.rowcount == 0:
        abort(404)
    db.commit()
    return redirect(url_for("admin"))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):
    db = get_db()
    cur = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    if cur.rowcount == 0:
        abort(404)
    db.commit()
    return redirect(url_for("admin"))


@app.route("/api/tasks")
def api_tasks():
    return jsonify(
        {
            "tasks": fetch_tasks(),
            "now": datetime.now().strftime("%H:%M"),
            "date": datetime.now().strftime("%A, %B %-d"),
        }
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=get_port(), debug=True)