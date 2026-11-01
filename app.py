from __future__ import annotations

import sqlite3
import hashlib
import json
import os
import urllib.request
import urllib.error
import tempfile
import zipfile
from collections import Counter
from io import BytesIO
from xml.sax.saxutils import escape
from datetime import date, datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "worklog.db"

app = Flask(__name__)


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
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
        todo_columns = {row["name"] for row in db.execute("PRAGMA table_info(todos)")}
        if "tags" not in todo_columns:
            db.execute("ALTER TABLE todos ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
        db.execute("CREATE TABLE IF NOT EXISTS report_summaries (kind TEXT NOT NULL, period TEXT NOT NULL, project TEXT NOT NULL, content TEXT NOT NULL, fingerprint TEXT NOT NULL, PRIMARY KEY(kind, period, project))")


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
    project = request.args.get("project", "").strip()
    include_undated = request.args.get("include_undated") == "1"
    clauses, params = [], []
    if status in {"open", "done"}:
        clauses.append("status = ?")
        params.append(status)
    dates = []
    if due_from:
        dates.append("due_on >= ?")
        params.append(due_from)
    if due_to:
        dates.append("due_on <= ?")
        params.append(due_to)
    if dates:
        clauses.append("(" + " AND ".join(dates) + (" OR due_on IS NULL" if include_undated else "") + ")")
    if project:
        clauses.append("(',' || replace(tags, '，', ',') || ',') LIKE ?")
        params.append(f"%,{project},%")
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
        if data.get("source_log_id") and not db.execute("SELECT 1 FROM work_logs WHERE id=?", (data["source_log_id"],)).fetchone():
            abort(400, "来源日志不存在")
        cursor = db.execute("INSERT INTO todos (title, due_on, source_log_id, tags) VALUES (?, ?, ?, ?)", (data["title"].strip(), data.get("due_on") or None, data.get("source_log_id") or None, data.get("tags", "").strip()))
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


@app.put("/api/todos/<int:todo_id>")
def edit_todo(todo_id: int):
    data = payload(("title",))
    with connection() as db:
        cursor = db.execute("UPDATE todos SET title=?, due_on=?, tags=? WHERE id=?", (data["title"].strip(), data.get("due_on") or None, data.get("tags", "").strip(), todo_id))
        if not cursor.rowcount:
            abort(404)
        row = db.execute("SELECT * FROM todos WHERE id=?", (todo_id,)).fetchone()
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
    groups = {}
    for log in logs:
        names = list(dict.fromkeys(x.strip() for x in log["tags"].replace("，", ",").split(",") if x.strip())) or ["未分类"]
        for name in names:
            groups.setdefault(name, []).append(row_dict(log))
    with connection() as db:
        saved = {row["project"]: row_dict(row) for row in db.execute("SELECT * FROM report_summaries WHERE kind=? AND period=?", (kind, period))}
    projects = []
    for name, entries in sorted(groups.items()):
        fingerprint = log_fingerprint(entries)
        summary = saved.get(name)
        projects.append({"name": name, "logs": entries, "summary": summary["content"] if summary else "", "changed": bool(summary and summary["fingerprint"] != fingerprint), "fingerprint": fingerprint})
    return jsonify({
        "kind": kind, "period": period, "log_count": len(logs), "todo_done": completed, "todo_open": open_count,
        "tags": sorted(tags.items(), key=lambda item: (-item[1], item[0])),
        "types": dict(Counter(x["work_type"] for x in logs)), "projects": projects,
        "highlights": [{"date": x["logged_on"], "title": x["title"], "content": x["content"]} for x in logs],
    })


def log_fingerprint(entries):
    return hashlib.sha256(json.dumps(entries, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@app.put("/api/summaries")
def save_summary():
    data = payload(("kind", "period", "project"))
    if data["kind"] not in ("month", "year"):
        abort(400)
    with connection() as db:
        db.execute("INSERT INTO report_summaries(kind,period,project,content,fingerprint) VALUES(?,?,?,?,?) ON CONFLICT(kind,period,project) DO UPDATE SET content=excluded.content,fingerprint=excluded.fingerprint", (data["kind"], data["period"], data["project"], data.get("content", ""), data.get("fingerprint", "")))
    return jsonify({"ok": True})


@app.post("/api/summaries/generate")
def generate_summary():
    data = payload(("kind", "period", "project"))
    config = read_ai_config()
    key = os.environ.get("OPENAI_API_KEY") or config.get("api_key")
    if not key:
        abort(400, "请先在本机配置 OPENAI_API_KEY")
    response = report(data["kind"], data["period"]).get_json()
    group = next((x for x in response["projects"] if x["name"] == data["project"]), None)
    if not group:
        abort(404, "该项目没有日志")
    prompt = "请根据以下工作日志，简洁概括该项目的主要进展、成果和待解决事项。不要捏造事实；信息不足请说明。\n" + json.dumps([{"日期": x["logged_on"], "标题": x["title"], "内容": x["content"]} for x in group["logs"]], ensure_ascii=False)
    body = json.dumps({"model": os.environ.get("OPENAI_MODEL") or config.get("model") or "gpt-4o-mini", "input": prompt}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/responses", data=body, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as result:
            result_data = json.load(result)
    except (urllib.error.URLError, TimeoutError):
        abort(502, "AI 服务连接失败，请检查配置和网络")
    content = "\n".join(part.get("text", "") for item in result_data.get("output", []) for part in item.get("content", []) if part.get("type") == "output_text")
    if not content:
        abort(502, "AI 服务没有返回总结")
    return jsonify({"content": content, "fingerprint": group["fingerprint"]})


AI_CONFIG_PATH = BASE_DIR / ".ai-config.json"


def read_ai_config():
    if not AI_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(AI_CONFIG_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


@app.get("/api/ai-settings")
def get_ai_settings():
    data = read_ai_config()
    return jsonify({"configured": bool(data.get("api_key") or os.environ.get("OPENAI_API_KEY")), "model": data.get("model", "gpt-4o-mini")})


@app.put("/api/ai-settings")
def save_ai_settings():
    data = payload()
    settings = read_ai_config()
    if data.get("api_key"):
        settings["api_key"] = data["api_key"].strip()
    settings["model"] = (data.get("model") or "gpt-4o-mini").strip()
    fd = os.open(AI_CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(settings, file)
    return jsonify({"configured": bool(settings.get("api_key")), "model": settings["model"]})


@app.post("/api/report-export")
def export_report():
    data = payload(("kind", "period", "format"))
    report_data = report(data["kind"], data["period"]).get_json()
    lines = [data["period"] + (" 工作月报" if data["kind"] == "month" else " 工作年报"), f"日志总数：{report_data['log_count']}", "工作类型：" + "、".join(f"{k} {v}" for k, v in report_data["types"].items())]
    for group in report_data["projects"]:
        lines.extend(["", group["name"], group["summary"] or "暂无项目总结"])
        lines.extend(f"{entry['logged_on']} {entry['title']} {entry['content']}" for entry in group["logs"])
    if data["format"] == "txt":
        return send_file(BytesIO("\n".join(lines).encode("utf-8-sig")), mimetype="text/plain", as_attachment=True, download_name="report.txt")
    if data["format"] != "docx":
        abort(400)
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        paragraphs = "".join('<w:p><w:r><w:t xml:space="preserve">' + escape(line) + '</w:t></w:r></w:p>' for text_line in lines for line in text_line.split('\n'))
        archive.writestr("word/document.xml", '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + paragraphs + '<w:sectPr/></w:body></w:document>')
    output.seek(0)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document", as_attachment=True, download_name="report.docx")


BACKUP_DIR = BASE_DIR / "backups"


def make_backup(prefix="auto"):
    BACKUP_DIR.mkdir(exist_ok=True)
    path = BACKUP_DIR / f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db"
    with connection() as source, sqlite3.connect(path) as target:
        source.backup(target)
    return path


def daily_backup():
    BACKUP_DIR.mkdir(exist_ok=True)
    if not list(BACKUP_DIR.glob(f"auto-{date.today():%Y%m%d}-*.db")):
        make_backup()
    backups = sorted(BACKUP_DIR.glob("auto-*.db"), reverse=True)
    for old in backups[30:]:
        old.unlink()


@app.get("/api/backup")
def download_backup():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "worklog-backup.db"
        with connection() as source, sqlite3.connect(path) as target:
            source.backup(target)
        data = BytesIO(path.read_bytes())
    return send_file(data, mimetype="application/vnd.sqlite3", as_attachment=True, download_name=f"worklog-{date.today()}.db")


@app.post("/api/restore")
def restore_backup():
    upload = request.files.get("backup")
    if not upload:
        abort(400, "请选择备份文件")
    with tempfile.TemporaryDirectory(dir=BASE_DIR) as folder:
        path = Path(folder) / "restore.db"
        upload.save(path)
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as source:
                if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    abort(400, "备份文件损坏")
                tables = {x[0] for x in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"work_logs", "todos", "projects"}.issubset(tables):
                    abort(400, "备份文件不是工作记录数据库")
                make_backup("before-restore")
                with connection() as destination:
                    source.backup(destination)
        except sqlite3.DatabaseError:
            abort(400, "无效的备份文件")
    init_db()
    return jsonify({"ok": True})


if __name__ == "__main__":
    daily_backup()
    app.run(debug=True, host="127.0.0.1", port=5000)

