from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "worklog.db"

app = Flask(__name__)


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    with connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS work_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_on TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_on TEXT,
                status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'done')),
                source_log_id INTEGER REFERENCES work_logs(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_logs_date ON work_logs(logged_on);
            CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(work_logs)")}
        if "work_type" not in columns:
            db.execute("ALTER TABLE work_logs ADD COLUMN work_type TEXT NOT NULL DEFAULT '其他'")


init_db()


def row_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def payload(required: tuple[str, ...] = ()) -> dict:
    data = request.get_json(silent=True) or {}
    for key in required:
        if not str(data.get(key, "")).strip():
            abort(400, f"缺少字段：{key}")
    return data


def valid_work_type(value: str | None) -> str:
    return value if value in {"开发", "管理", "文档", "其他"} else "其他"


@app.get("/")
def home():
    return render_template("index.html", today=date.today().isoformat())


@app.get("/api/logs")
def list_logs():
    month = request.args.get("month", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    work_type = request.args.get("work_type", "").strip()
    project = request.args.get("project", "").strip()
    keyword = request.args.get("keyword", "").strip()
    clauses, params = [], []
    if month:
        clauses.append("logged_on LIKE ?")
        params.append(f"{month}%")
    if date_from:
        clauses.append("logged_on >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("logged_on <= ?")
        params.append(date_to)
    if work_type:
        clauses.append("work_type = ?")
        params.append(work_type)
    if project:
        clauses.append("(',' || replace(tags, '，', ',') || ',') LIKE ?")
        params.append(f"%,{project},%")
    if keyword:
        clauses.append("(title LIKE ? OR content LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    with connection() as db:
        query = "SELECT * FROM work_logs"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        rows = db.execute(query + " ORDER BY logged_on DESC, id DESC", params).fetchall()
    return jsonify([row_dict(row) for row in rows])


@app.post("/api/logs")
def create_log():
    data = payload(("title",))
    with connection() as db:
        cursor = db.execute(
            "INSERT INTO work_logs (logged_on, title, content, tags, work_type) VALUES (?, ?, ?, ?, ?)",
            (data.get("logged_on") or date.today().isoformat(), data["title"].strip(), data.get("content", "").strip(), data.get("tags", "").strip(), valid_work_type(data.get("work_type"))),
        )
        row = db.execute("SELECT * FROM work_logs WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(row_dict(row)), 201


@app.put("/api/logs/<int:log_id>")
def update_log(log_id: int):
    data = payload(("title",))
    with connection() as db:
        cursor = db.execute(
            "UPDATE work_logs SET logged_on=?, title=?, content=?, tags=?, work_type=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (data.get("logged_on") or date.today().isoformat(), data["title"].strip(), data.get("content", "").strip(), data.get("tags", "").strip(), valid_work_type(data.get("work_type")), log_id),
        )
        if not cursor.rowcount:
            abort(404)
        row = db.execute("SELECT * FROM work_logs WHERE id = ?", (log_id,)).fetchone()
    return jsonify(row_dict(row))


@app.delete("/api/logs/<int:log_id>")
def delete_log(log_id: int):
    with connection() as db:
        db.execute("DELETE FROM work_logs WHERE id = ?", (log_id,))
    return "", 204


@app.get("/api/projects")
def list_projects():
    with connection() as db:
        rows = db.execute("SELECT * FROM projects ORDER BY name COLLATE NOCASE").fetchall()
    return jsonify([row_dict(row) for row in rows])


@app.post("/api/projects")
def create_project():
    data = payload(("name",))
    try:
        with connection() as db:
            cursor = db.execute("INSERT INTO projects (name) VALUES (?)", (data["name"].strip(),))
            row = db.execute("SELECT * FROM projects WHERE id=?", (cursor.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        abort(400, "项目标签已存在")
    return jsonify(row_dict(row)), 201


@app.delete("/api/projects/<int:project_id>")
def delete_project(project_id: int):
    with connection() as db:
        db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    return "", 204


@app.get("/api/todos")
def list_todos():
    status = request.args.get("status", "").strip()
    due_from = request.args.get("due_from", "").strip()
    due_to = request.args.get("due_to", "").strip()
    keyword = request.args.get("keyword", "").strip()
    clauses, params = [], []
    if status in {"open", "done"}:
        clauses.append("status = ?")
        params.append(status)
    if due_from:
        clauses.append("due_on >= ?")
        params.append(due_from)
    if due_to:
        clauses.append("due_on <= ?")
        params.append(due_to)
    if keyword:
        clauses.append("title LIKE ?")
        params.append(f"%{keyword}%")
    with connection() as db:
        query = "SELECT * FROM todos"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        rows = db.execute(query + " ORDER BY status, COALESCE(due_on, '9999-12-31'), id DESC", params).fetchall()
    return jsonify([row_dict(row) for row in rows])


@app.post("/api/todos")
def create_todo():
    data = payload(("title",))
    with connection() as db:
        cursor = db.execute("INSERT INTO todos (title, due_on, source_log_id) VALUES (?, ?, ?)", (data["title"].strip(), data.get("due_on") or None, data.get("source_log_id") or None))
        row = db.execute("SELECT * FROM todos WHERE id=?", (cursor.lastrowid,)).fetchone()
    return jsonify(row_dict(row)), 201


@app.patch("/api/todos/<int:todo_id>")
def update_todo(todo_id: int):
    data = payload()
    status = data.get("status")
    if status not in ("open", "done"):
        abort(400, "状态无效")
    with connection() as db:
        db.execute("UPDATE todos SET status=? WHERE id=?", (status, todo_id))
        row = db.execute("SELECT * FROM todos WHERE id=?", (todo_id,)).fetchone()
    if row is None:
        abort(404)
    return jsonify(row_dict(row))


@app.delete("/api/todos/<int:todo_id>")
def delete_todo(todo_id: int):
    with connection() as db:
        db.execute("DELETE FROM todos WHERE id=?", (todo_id,))
    return "", 204


@app.get("/api/reports/<kind>/<period>")
def report(kind: str, period: str):
    expected = 7 if kind == "month" else 4
    try:
        datetime.strptime(period, "%Y-%m" if kind == "month" else "%Y")
    except ValueError:
        abort(400, "时间格式无效")
    if kind not in ("month", "year") or len(period) != expected:
        abort(400, "报表类型无效")
    with connection() as db:
        logs = db.execute("SELECT * FROM work_logs WHERE logged_on LIKE ? ORDER BY logged_on", (f"{period}%",)).fetchall()
        todo_counts = db.execute(
            "SELECT status, COUNT(*) count FROM todos WHERE substr(created_at, 1, ?) = ? GROUP BY status", (expected, period)
        ).fetchall()
    completed = next((x["count"] for x in todo_counts if x["status"] == "done"), 0)
    open_count = next((x["count"] for x in todo_counts if x["status"] == "open"), 0)
    tags: dict[str, int] = {}
    for log in logs:
        for tag in log["tags"].replace("，", ",").split(","):
            if tag.strip():
                tags[tag.strip()] = tags.get(tag.strip(), 0) + 1
    return jsonify({
        "kind": kind, "period": period, "log_count": len(logs), "todo_done": completed, "todo_open": open_count,
        "tags": sorted(tags.items(), key=lambda item: (-item[1], item[0])),
        "highlights": [{"date": x["logged_on"], "title": x["title"], "content": x["content"]} for x in logs],
    })


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)

