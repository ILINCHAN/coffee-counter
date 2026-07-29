"""
咖啡机使用记录 - 共享后端（仅录入数字）
所有人访问同一地址，录入的数字实时共享同步。
部署版：SQLite 持久化 + 读取 PORT 环境变量。
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime, date
from contextlib import closing

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=None)
CORS(app)

# 优先用 DATA_DIR（Render 挂载的持久磁盘 /data），不可写时回退到源码目录
_preferred = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
try:
    os.makedirs(_preferred, exist_ok=True)
    _test = os.path.join(_preferred, ".write_test")
    with open(_test, "w") as f:
        f.write("ok")
    os.remove(_test)
    BASE_DIR = _preferred
except OSError:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(BASE_DIR, exist_ok=True)
DB_FILE = os.path.join(BASE_DIR, "coffee.db")


def _db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""CREATE TABLE IF NOT EXISTS records (
        id TEXT PRIMARY KEY,
        cnt INTEGER NOT NULL,
        time TEXT NOT NULL
    )""")
    return conn


def _load():
    with closing(_db()) as conn:
        rows = conn.execute("SELECT id, cnt, time FROM records").fetchall()
    return [{"id": r[0], "count": r[1], "time": r[2]} for r in rows]


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
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "index.html")


@app.route("/<path:fname>")
def static_files(fname):
    # 仅放行已知静态资源，避免目录穿越
    allowed = {"manifest.json", "icon.svg", "icon-192.png", "icon-512.png",
               "apple-touch-icon.png", "favicon.ico", "flower.svg"}
    base = os.path.dirname(os.path.abspath(__file__))
    if fname not in allowed:
        return jsonify({"error": "not found"}), 404
    return send_from_directory(base, fname)


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
    with closing(_db()) as conn:
        conn.execute("INSERT INTO records (id, cnt, time) VALUES (?,?,?)",
                     (record["id"], record["count"], record["time"]))
        conn.commit()
    data = _load()
    return jsonify({"record": record, "stats": _stats(data)}), 201


@app.route("/api/records/<rid>", methods=["DELETE"])
def delete_record(rid):
    with closing(_db()) as conn:
        cur = conn.execute("DELETE FROM records WHERE id = ?", (rid,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "记录不存在"}), 404
    return jsonify({"stats": _stats(_load())})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
