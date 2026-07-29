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
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json as _json

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


# ---------- Turso HTTP API (无第三方依赖,只走 urllib) ----------
def _turso_call(stmts):
    """
    stmts: list of {"sql": str, "args": [{"type": "text"|"integer", "value": str|int}]} (args 可选)
    返回: results list
    """
    payload = []
    for s in stmts:
        item = {"q": s["sql"]}
        if s.get("args"):
            item["args"] = [{"type": a["type"], "value": a["value"]} for a in s["args"]]
        payload.append(item)
    body = _json.dumps({"statements": payload}).encode()
    req = Request(
        f"{TURSO_URL}/v2/pipeline",
        data=body,
        headers={
            "Authorization": f"Bearer {TURSO_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read().decode())
    except HTTPError as e:
        try:
            err_body = e.read().decode()
        except Exception:
            err_body = ""
        raise RuntimeError(f"Turso HTTP {e.code}: {err_body}")
    except URLError as e:
        raise RuntimeError(f"Turso URL error: {e}")
    return data.get("results", [])


def _check(results):
    """检查 results 里每个 statement 是否成功,失败抛错"""
    for r in results:
        if "error" in r:
            raise RuntimeError(f"Turso SQL error: {r['error']}")


def _arg(v):
    """把 Python 值转 Turso 参数"""
    if isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    return {"type": "text", "value": str(v)}


def _turso_init():
    res = _turso_call([{"sql":
        "CREATE TABLE IF NOT EXISTS records "
        "(id TEXT PRIMARY KEY, cnt INTEGER NOT NULL, time TEXT NOT NULL)"}])
    _check(res)


# ---------- 统一读写 ----------
def _load():
    if USE_TURSO:
        _turso_init()
        res = _turso_call([{"sql": "SELECT id, cnt, time FROM records"}])
        _check(res)
        rows = res[0].get("response", {}).get("result", {}).get("rows", []) or []
        cols = res[0].get("response", {}).get("result", {}).get("col_names", []) or []
        out = []
        for row in rows:
            entry = dict(zip(cols, row))
            out.append({
                "id": entry["id"],
                "count": int(entry["cnt"]),
                "time": entry["time"],
            })
        return out
    with closing(_sqlite_conn()) as conn:
        rows = conn.execute("SELECT id, cnt, time FROM records").fetchall()
    return [{"id": r[0], "count": r[1], "time": r[2]} for r in rows]


def _insert(rid, cnt, t):
    if USE_TURSO:
        res = _turso_call([{"sql":
            "INSERT INTO records (id, cnt, time) VALUES (?, ?, ?)",
            "args": [_arg(rid), _arg(cnt), _arg(t)]}])
        _check(res)
        return
    with closing(_sqlite_conn()) as conn:
        conn.execute("INSERT INTO records (id, cnt, time) VALUES (?,?,?)",
                     (rid, cnt, t))
        conn.commit()


def _delete(rid):
    if USE_TURSO:
        res = _turso_call([{"sql":
            "DELETE FROM records WHERE id = ?",
            "args": [_arg(rid)]}])
        _check(res)
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
