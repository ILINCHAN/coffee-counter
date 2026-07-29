"""
咖啡机使用记录 - 共享后端（仅录入数字）
所有人访问同一地址，录入的数字实时共享同步。

持久化策略（优先级）：
1. 若设置了 TURSO_URL + TURSO_TOKEN（Turso 免费云 SQLite），使用它，数据集中持久不丢
2. 否则回退到本地 SQLite（开发/调试用）

Turso HTTP API 严格按官方文档 /v2/pipeline:
  body: {"requests": [{"type":"execute","stmt":{"sql":"...","args":[...]}}]}
  resp: results[i].response.result.cols / rows / affected_row_count
"""
import os
import sqlite3
import uuid
from datetime import datetime, date, timezone, timedelta
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
TURSO_URL = os.environ.get("TURSO_URL", "")
# Turso 控制台给的 URL 是 libsql:// 开头，但 urllib 只认 http/https
if TURSO_URL.startswith("libsql://"):
    TURSO_URL = "https://" + TURSO_URL[len("libsql://"):]
TURSO_URL = TURSO_URL.rstrip("/")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")
USE_TURSO = bool(TURSO_URL and TURSO_TOKEN)


# ---------- SQLite 回退 ----------
def _sqlite_conn():
    db_file = os.path.join(BASE_DIR, "coffee.db")
    conn = sqlite3.connect(db_file)
    conn.execute("""CREATE TABLE IF NOT EXISTS records (
        id TEXT PRIMARY KEY, cnt INTEGER NOT NULL, time TEXT NOT NULL, note TEXT)""")
    # 兼容旧库：若缺 note 列则补上
    cols = [r[1] for r in conn.execute("PRAGMA table_info(records)").fetchall()]
    if "note" not in cols:
        try:
            conn.execute("ALTER TABLE records ADD COLUMN note TEXT")
        except sqlite3.OperationalError:
            pass
    return conn


# ---------- Turso HTTP API (严格按 /v2/pipeline 文档) ----------
def _turso_call(sql, args=None):
    """
    单 SQL 直发，返回 (ok_dict, error_msg)。
    ok_dict 包含 keys: affected_row_count, rows[], cols[]
    若 ok_dict 为 None 说明发生 error_msg 描述的错误。
    """
    stmt = {"sql": sql}
    if args:
        # args 每个元素已是 {"type":..,"value":...}
        stmt["args"] = args
    body = _json.dumps({
        "requests": [
            {"type": "execute", "stmt": stmt},
            {"type": "close"},
        ]
    }).encode()
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

    # 顶层 error
    if data.get("error"):
        return None, f"Turso top error: {data['error']}"

    results = data.get("results") or []
    if not results:
        return None, "Turso: empty results"

    # 第一个 statement 应该是 execute 的结果
    for r in results:
        rtype = r.get("type")
        if rtype == "error":
            err = r.get("error", {})
            return None, f"Turso SQL error: {err}"
        if rtype == "ok":
            inner = r.get("response", {})
            if inner.get("type") == "execute":
                return inner.get("result", {}), None

    return None, "Turso: no execute result found"


def _turso_init():
    res, err = _turso_call(
        "CREATE TABLE IF NOT EXISTS records "
        "(id TEXT PRIMARY KEY, cnt INTEGER NOT NULL, time TEXT NOT NULL, note TEXT)"
    )
    if err:
        raise RuntimeError(f"init: {err}")
    # 兼容旧库：若缺 note 列则补上（libSQL 支持 ADD COLUMN）
    try:
        _turso_call("ALTER TABLE records ADD COLUMN note TEXT")
    except Exception:
        pass
    return res


def _turso_exec_write(sql, args):
    res, err = _turso_call(sql, args)
    if err:
        raise RuntimeError(f"write: {err}")
    return res


def _turso_exec_select(sql, args=None):
    res, err = _turso_call(sql, args)
    if err:
        raise RuntimeError(f"select: {err}")
    # 解析 rows（按官方文档 rows 是 [[{type,value},...], ...]）
    rows = res.get("rows", []) or []
    cols = res.get("cols", []) or []
    col_names = [c.get("name") for c in cols]
    out = []
    for row in rows:
        entry = {}
        for i, cell in enumerate(row):
            if i < len(col_names) and col_names[i]:
                v = cell.get("value") if isinstance(cell, dict) else cell
                entry[col_names[i]] = v
        # 保证 note 字段存在
        entry.setdefault("note", "")
        out.append(entry)
    return out


# ---------- 统一读写 ----------
def _load():
    if USE_TURSO:
        _turso_init()
        rows = _turso_exec_select("SELECT id, cnt, time, note FROM records")
        return [{"id": r["id"], "count": int(r["cnt"]),
                 "time": r["time"], "note": r.get("note") or ""} for r in rows]
    with closing(_sqlite_conn()) as conn:
        rows = conn.execute("SELECT id, cnt, time, note FROM records").fetchall()
    return [{"id": r[0], "count": r[1], "time": r[2], "note": r[3] or ""} for r in rows]


def _insert(rid, cnt, t, note=""):
    note = (note or "")[:40]  # 限制长度，防止滥用
    if USE_TURSO:
        # 注意：value 必须是字符串
        args = [
            {"type": "text", "value": str(rid)},
            {"type": "integer", "value": str(int(cnt))},
            {"type": "text", "value": str(t)},
            {"type": "text", "value": str(note)},
        ]
        _turso_exec_write(
            "INSERT INTO records (id, cnt, time, note) VALUES (?, ?, ?, ?)", args)
        return
    with closing(_sqlite_conn()) as conn:
        conn.execute("INSERT INTO records (id, cnt, time, note) VALUES (?,?,?,?)",
                     (rid, cnt, t, note))
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
    note = str(body.get("note", "") or "").strip()[:40]
    # 北京时间存储（naive，不带时区后缀，前端按本地时间解析不会错乱）
    bj_now = datetime.utcnow() + timedelta(hours=8)
    record = {
        "id": uuid.uuid4().hex[:8],
        "count": count,
        "time": bj_now.strftime("%Y-%m-%dT%H:%M:%S"),
        "note": note,
    }
    _insert(record["id"], record["count"], record["time"], record["note"])
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
        try:
            _turso_init()
            info["turso_ok"] = True
        except Exception as e:
            info["turso_ok"] = False
            info["error"] = str(e)
    return jsonify(info)


@app.errorhandler(Exception)
def all_exception_handler(e):
    return jsonify({
        "error": "server_error",
        "message": str(e),
        "type": type(e).__name__,
        "trace": traceback.format_exc()[:800],
    }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
