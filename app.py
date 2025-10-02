from flask import Flask, render_template, request, redirect, url_for, g, abort
import sqlite3
import os                         # NEW
from pathlib import Path
from datetime import datetime, date

app = Flask(__name__)

# Portable data path (works locally and on Render)
DATA_DIR = Path(os.getenv("DATA_DIR", "."))   # Render will set DATA_DIR=/var/data
DATABASE = DATA_DIR / "data.db"               # <— use this instead of Path("data.db")


# --- Next match settings ---
NEXT_MATCH_DATE = datetime(2025, 10, 9, 20, 0)   # 9 Oct 2025, 20:00
NEXT_MATCH_END  = datetime(2025, 10, 9, 22, 0)   # 9 Oct 2025, 22:00


app = Flask(__name__)  # <-- must be named exactly "app"
print("Template folder:", app.template_folder)  # should print 'templates'

DATABASE = Path("data.db")
LEVELS = ["beginner", "for-fun", "competitive"]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DATABASE))
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS signups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name  TEXT NOT NULL,
            level      TEXT NOT NULL CHECK(level IN ('beginner','for-fun','competitive')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.commit()


@app.before_request
def ensure_db():
    init_db()


def fetch_players(level: str):
    db = get_db()
    rows = db.execute(
        "SELECT id, first_name, last_name FROM signups WHERE level=? "
        "ORDER BY created_at ASC, id ASC",
        (level,),
    ).fetchall()
    return [dict(id=r["id"], name=f"{r['first_name']} {r['last_name']}") for r in rows]


def split_groups(players, size=4):
    """
    Returns:
      full_groups: list of groups with exactly 'size' members
      forming_group: the last partial group (1-3 members) or None
    """
    groups = [players[i:i+size] for i in range(0, len(players), size)]
    full_groups = [g for g in groups if len(g) == size]
    forming_group = groups[-1] if groups and len(groups[-1]) < size else None
    return full_groups, forming_group

@app.context_processor
def inject_next_match():
    days_left = (NEXT_MATCH_DATE.date() - date.today()).days
    return {
        "next_match_date": NEXT_MATCH_DATE,
        "next_match_end": NEXT_MATCH_END,
        "days_left": days_left,
    }

@app.route("/join", methods=["POST"])
def join():
    first = request.form.get("first_name", "").strip()
    last = request.form.get("last_name", "").strip()
    level = request.form.get("level", "")

    if not first or not last or level not in LEVELS:
        abort(400, "Please provide first name, last name, and a valid level.")

    db = get_db()
    cur = db.execute(
        "INSERT INTO signups (first_name, last_name, level) VALUES (?, ?, ?)",
        (first, last, level),
    )
    db.commit()
    signup_id = cur.lastrowid
    return redirect(url_for("thanks", signup_id=signup_id))


@app.get("/thanks/<int:signup_id>")
def thanks(signup_id):
    db = get_db()
    row = db.execute(
        "SELECT id, first_name, last_name, level FROM signups WHERE id=?", (signup_id,)
    ).fetchone()
    if not row:
        abort(404)

    level = row["level"]
    players = fetch_players(level)
    ids = [p["id"] for p in players]
    idx = ids.index(signup_id)  # position within this level's queue

    # NEW: use split_groups instead of chunk_groups
    full_groups, forming_group = split_groups(players)

    # 1-based group number
    group_num = idx // 4 + 1

    if group_num <= len(full_groups):
        group_members = full_groups[group_num - 1]
        is_full = True
    else:
        group_members = forming_group or []
        is_full = len(group_members) == 4

    player_name = f"{row['first_name']} {row['last_name']}"
    return render_template(
        "thanks.html",
        player=player_name,
        level=level,
        group_num=group_num,
        group_members=group_members,
        is_full=is_full,
    )




@app.route("/reset", methods=["POST"])
def reset():
    # very simple protection — change ADMIN_KEY in env for production use
    key = request.form.get("key", "")
    admin_key = app.config.get("ADMIN_KEY") or "letmein"
    if key != admin_key:
        abort(403, "Forbidden")
    db = get_db()
    db.execute("DELETE FROM signups")
    db.commit()
    return redirect(url_for("index"))


if __name__ == "__main__":
    # Local dev: python app.py
    app.run(debug=True)
@app.get("/health")
def health():
    return "OK"

from flask import render_template

LEVELS = ["beginner", "for-fun", "competitive"]

@app.route("/", methods=["GET"])
def index():
    data = {}
    for level in LEVELS:
        players = fetch_players(level)
        full_groups, forming_group = split_groups(players)
        data[level] = {"full": full_groups, "forming": forming_group}

    # calculate countdown
    days_left = (NEXT_MATCH_DATE.date() - date.today()).days

    return render_template(
        "index.html",
        data=data,
        levels=LEVELS,
        next_match_date=NEXT_MATCH_DATE,
        next_match_end=NEXT_MATCH_END,
        days_left=days_left
    )
if __name__ == "__main__":
    app.run(debug=True)

