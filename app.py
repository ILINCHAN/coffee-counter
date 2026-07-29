"""
咖啡机使用记录 - 共享后端（仅录入数字）
所有人访问同一地址，录入的数字实时共享同步。

持久化策略（优先级）：
1. 若设置了 TURSO_URL + TURSO_TOKEN（Turso 免费云 SQLite），使用它，数据集中持久不丢
2. 否则回退到本地 SQLite（开发/调试用）
"""
import os
import sqlite3
import uuid
from datetime import datetime, date
from contextlib import closing

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=None)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TURSO_URL = os.environ.get("TURSO_URL", "").rstrip("/")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")
USE_TURSO = bool(TURSO_URL and TURSO_TOKEN)


# ---------- SQLite 回退 ----------
def _sqlite_conn():
    db_file = os.path.join(BASE_DIR, "coffee.db")
    conn = sqlite3.connect(db_file)
    conn.execute("""CREATE TABLE IF NOT EXISTS records (
        id TEXT PRIMARY KEY, cnt INTEGER NOT NULL, time TEXT NOT NULL)""")
    return conn


# ---------- Turso 客户端 ----------
def _turso_client():
    from libsql_client import create_client
    return create_client(url=TURSO_URL, auth_token=TURSO_TOKEN)


def _turso_init():
    _turso_client().execute(
        "CREATE TABLE IF NOT EXISTS records "
        "(id TEXT PRIMARY KEY, cnt INTEGER NOT NULL, time TEXT NOT NULL)"
    )


# ---------- 统一读写 ----------
def _load():
    if USE_TURSO:
        _turso_init()
        res = _turso_client().execute("SELECT id, cnt, time FROM records")
        # libsql-client 返回 res.rows：每行是 dict 或 tuple
        out = []
        for r in res.rows:
            if isinstance(r, dict):
                out.append({"id": r["id"], "count": int(r["cnt"]), "time": r["time"]})
            else:
                out.append({"id": r[0], "count": int(r[1]), "time": r[2]})
        return out
    with closing(_sqlite_conn()) as conn:
        rows = conn.execute("SELECT id, cnt, time FROM records").fetchall()
    return [{"id": r[0], "count": r[1], "time": r[2]} for r in rows]


def _insert(rid, cnt, t):
    if USE_TURSO:
        _turso_client().execute(
            "INSERT INTO records (id, cnt, time) VALUES (?, ?, ?)",
            [rid, cnt, t],
        )
        return
    with closing(_sqlite_conn()) as conn:
        conn.execute("INSERT INTO records (id, cnt, time) VALUES (?,?,?)",
                     (rid, cnt, t))
        conn.commit()


def _delete(rid):
    if USE_TURSO:
        _turso_client().execute("DELETE FROM records WHERE id = ?", [rid])
        return 1
    with closing(_sqlite_conn()) as conn:
        cur = conn.execute("DELETE FROM records WHERE id = ?", (rid,))
        conn.commit()
        return cur.rowcount


def _stats(records):
    total = sum(r["count"] for r in records)
    today = date.today().isoformat()
    today_count = sum(
        r["count"] for r in records
        if datetime.fromisoformat(r["time"]).date().isoformat() == today
    )
    return {"total": total, "today": today_count, "entries": len(records)}


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:fname>")
def static_files(fname):
    allowed = {"manifest.json", "icon.svg", "icon-192.png", "icon-512.png",
               "apple-touch-icon.png", "favicon.ico", "flower.svg"}
    if fname not in allowed:
        return jsonify({"error": "not found"}), 404
    return send_from_directory(BASE_DIR, fname)


@app.route("/api/records", methods=["GET"])
def list_records():
    data = _load()
    records = sorted(data, key=lambda r: r["time"], reverse=True)
    return jsonify({"records": records, "stats": _stats(data)})


@app.route("/api/records", methods=["POST"])
def add_record():
    body = request.get_json(silent=True) or {}
    try:
        count = int(body.get("count", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "数字无效"}), 400
    if count <= 0:
        return jsonify({"error": "请输入大于0的数字"}), 400
    if count > 99:
        return jsonify({"error": "单次最多99"}), 400
    record = {
        "id": uuid.uuid4().hex[:8],
        "count": count,
        "time": datetime.now().isoformat(timespec="seconds"),
    }
    _insert(record["id"], record["count"], record["time"])
    data = _load()
    return jsonify({"record": record, "stats": _stats(data)}), 201


@app.route("/api/records/<rid>", methods=["DELETE"])
def delete_record(rid):
    rowcount = _delete(rid)
    if rowcount == 0:
        return jsonify({"error": "记录不存在"}), 404
    return jsonify({"stats": _stats(_load())})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"db": "turso" if USE_TURSO else "sqlite"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
