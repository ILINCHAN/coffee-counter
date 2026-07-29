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
import traceback

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


# ---------- Turso HTTP API ----------
def _turso_call(sql, args=None):
    """
    一个 SQL 直接发,使用 /v2/pipeline 端点,格式与官方文档一致。
    返回 (results, error_msg)
    """
    stmt = {"q": sql}
    if args:
        # Turso 期望 args 是 list[{"type": "text|integer|...", "value": ...}]
        # 每个 value 必须是 string
        stmt["args"] = args
    body = _json.dumps({"requests": [{"type": "execute", "stmt": stmt}]}).encode()
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
        with urlopen(req, timeout=20) as resp:
            data = _json.loads(resp.read().decode())
        # 用 requests 模式时,response key 是 'results'
        results = data.get("results", [])
        err = data.get("error")
        if err:
            return None, f"Turso error: {err}"
        # 检查每个 result
        out = []
        for r in results:
            if "response" in r:
                out.append(r["response"])
            elif "error" in r:
                return None, f"Turso SQL error: {r['error']}"
        return out, None
    except HTTPError as e:
        try:
            err_body = e.read().decode()
        except Exception:
            err_body = ""
        return None, f"Turso HTTP {e.code}: {err_body[:300]}"
    except URLError as e:
        return None, f"Turso URL error: {e}"
    except Exception as e:
        return None, f"Turso unknown error: {e}"


def _turso_init():
    res, err = _turso_call(
        "CREATE TABLE IF NOT EXISTS records "
        "(id TEXT PRIMARY KEY, cnt INTEGER NOT NULL, time TEXT NOT NULL)"
    )
    if err:
        raise RuntimeError(f"init: {err}")
    return res


def _turso_exec_write(sql, args):
    res, err = _turso_call(sql, args)
    if err:
        raise RuntimeError(f"write: {err}")
    return res


def _turso_exec_select(sql):
    res, err = _turso_call(sql)
    if err:
        raise RuntimeError(f"select: {err}")
    if not res:
        return []
    result_obj = res[0].get("result", {})
    rows = result_obj.get("rows", []) or []
    cols = result_obj.get("col_names", []) or []
    return [dict(zip(cols, row)) for row in rows]


# ---------- 统一读写 ----------
def _load():
    if USE_TURSO:
        _turso_init()
        rows = _turso_exec_select("SELECT id, cnt, time FROM records")
        return [{"id": r["id"], "count": int(r["cnt"]), "time": r["time"]} for r in rows]
    with closing(_sqlite_conn()) as conn:
        rows = conn.execute("SELECT id, cnt, time FROM records").fetchall()
    return [{"id": r[0], "count": r[1], "time": r[2]} for r in rows]


def _insert(rid, cnt, t):
    if USE_TURSO:
        # Turso pipeline 参数格式:value 必须是字符串
        args = [
            {"type": "text", "value": str(rid)},
            {"type": "integer", "value": str(int(cnt))},
            {"type": "text", "value": str(t)},
        ]
        _turso_exec_write("INSERT INTO records (id, cnt, time) VALUES (?, ?, ?)", args)
        return
    with closing(_sqlite_conn()) as conn:
        conn.execute("INSERT INTO records (id, cnt, time) VALUES (?,?,?)",
                     (rid, cnt, t))
        conn.commit()


def _delete(rid):
    if USE_TURSO:
        args = [{"type": "text", "value": str(rid)}]
        _turso_exec_write("DELETE FROM records WHERE id = ?", args)
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
    info = {"db": "turso" if USE_TURSO else "sqlite"}
    if USE_TURSO:
        info["url"] = TURSO_URL
        # 探测一下,看真实错误
        try:
            _turso_init()
            info["turso_ok"] = True
        except Exception as e:
            info["turso_ok"] = False
            info["error"] = str(e)
    return jsonify(info)


@app.errorhandler(Exception)
def all_exception_handler(e):
    # 所有未捕获异常都返回 JSON 而不是 HTML
    return jsonify({
        "error": "server_error",
        "message": str(e),
        "type": type(e).__name__,
        "trace": traceback.format_exc()[:800],
    }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
