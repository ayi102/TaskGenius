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

CATEGORIES = ("idris", "elina", "jenin", "kitchen", "cleaning", "therapy", "other")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

app = Flask(__name__)


@app.template_filter("fmt12")
def fmt12(hhmm):
    if not hhmm:
        return "—"
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except (ValueError, AttributeError):
        return hhmm
    ampm = "pm" if h >= 12 else "am"
    return f"{h % 12 or 12}:{m:02d}{ampm}"


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
    scheduled_time = (form.get("scheduled_time") or "").strip()
    picked_cats = [c for c in form.getlist("categories") if c in CATEGORIES]
    # Preserve canonical order (matches CATEGORIES tuple) so storage is stable.
    cats_ordered = [c for c in CATEGORIES if c in picked_cats]
    category = ",".join(cats_ordered)
    picked_days = [d for d in form.getlist("days") if d in DAYS]
    days_of_week = ",".join(picked_days) if picked_days and len(picked_days) < len(DAYS) else None

    errors = []
    if not title:
        errors.append("Title is required.")
    if not cats_ordered:
        errors.append("Pick at least one category.")
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


def tasks_on_day(tasks, day):
    return [t for t in tasks if not t["days_of_week"] or day in t["days_of_week"].split(",")]


def pick_featured(today_tasks, now_dt=None):
    """Return (task_id, kind) where kind is 'now' if a task is within ±60 min of
    the current time, else 'next' if there's an upcoming task today, else (None, None)."""
    now_dt = now_dt or datetime.now()
    now_min = now_dt.hour * 60 + now_dt.minute

    best_now, best_diff = None, 61
    next_up, next_min = None, 24 * 60 + 1
    for t in today_tasks:
        if not t["scheduled_time"]:
            continue
        try:
            h, m = (int(x) for x in t["scheduled_time"].split(":"))
        except ValueError:
            continue
        tm = h * 60 + m
        diff = abs(tm - now_min)
        if diff < best_diff:
            best_now, best_diff = t, diff
        if now_min < tm < next_min:
            next_up, next_min = t, tm

    if best_now:
        return best_now["id"], "now"
    if next_up:
        return next_up["id"], "next"
    return None, None


@app.route("/")
def display():
    return render_template(
        "display.html",
        categories=CATEGORIES,
        lan_ip=get_lan_ip(),
        port=get_port(),
    )


def _admin_context(form=None, errors=None, editing_id=None):
    all_tasks = fetch_tasks()
    day_filter = request.args.get("day")
    if day_filter not in DAYS:
        day_filter = None
    tasks = tasks_on_day(all_tasks, day_filter) if day_filter else all_tasks
    return {
        "tasks": tasks,
        "categories": CATEGORIES,
        "days": DAYS,
        "form": form or {},
        "errors": errors or [],
        "editing_id": editing_id,
        "selected_day": day_filter,
        "day_counts": {d: len(tasks_on_day(all_tasks, d)) for d in DAYS},
        "total_tasks": len(all_tasks),
    }


@app.route("/admin")
def admin():
    edit_id = request.args.get("edit", type=int)
    return render_template("admin.html", **_admin_context(editing_id=edit_id))


@app.route("/week")
def week():
    all_tasks = fetch_tasks()
    tasks_by_day = {d: tasks_on_day(all_tasks, d) for d in DAYS}
    today_key = DAYS[datetime.now().weekday()]
    featured_id, featured_kind = pick_featured(tasks_by_day[today_key])
    return render_template(
        "week.html",
        days=DAYS,
        tasks_by_day=tasks_by_day,
        day_counts={d: len(tasks_by_day[d]) for d in DAYS},
        total_tasks=len(all_tasks),
        today_key=today_key,
        featured_id=featured_id,
        featured_kind=featured_kind,
    )


def _admin_redirect():
    day = request.args.get("day")
    return redirect(url_for("admin", day=day) if day in DAYS else url_for("admin"))


@app.route("/tasks", methods=["POST"])
def create_task():
    data, errors = parse_form(request.form)
    if errors:
        return render_template("admin.html", **_admin_context(form=data, errors=errors)), 400

    db = get_db()
    db.execute(
        "INSERT INTO tasks (title, notes, category, scheduled_time, days_of_week) VALUES (?, ?, ?, ?, ?)",
        (data["title"], data["notes"], data["category"], data["scheduled_time"], data["days_of_week"]),
    )
    db.commit()
    return _admin_redirect()


@app.route("/tasks/<int:task_id>/edit", methods=["POST"])
def edit_task(task_id):
    data, errors = parse_form(request.form)
    if errors:
        return render_template("admin.html", **_admin_context(
            form={**data, "id": task_id}, errors=errors, editing_id=task_id,
        )), 400

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
    return _admin_redirect()


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):
    db = get_db()
    cur = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    if cur.rowcount == 0:
        abort(404)
    db.commit()
    return _admin_redirect()


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