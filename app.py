import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, session

app = Flask(__name__)
app.secret_key = "secret_key_for_inventory_app"

print("DB path:", os.path.abspath("inventory.db"))


def add_log(action, item_name):
    """操作ログを追加"""
    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (user, action, item_name, created_at) VALUES (?, ?, ?, ?)",
        (
            session.get("username"),
            action,
            item_name,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    conn.commit()
    conn.close()


def init_db():
    """DB初期化"""
    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()

    # users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    # items
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            quantity INTEGER,
            unit TEXT
        )
    """)

    # logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            action TEXT,
            item_name TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def create_admin():
    """管理者アカウント作成"""
    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
        ("admin", "admin", "admin")
    )
    conn.commit()
    conn.close()


# ====== ルート ======
@app.route("/")
def index():
    if "username" not in session:
        return redirect("/login")

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name, quantity, unit FROM items")
    items = cur.fetchall()
    conn.close()

    return render_template("index.html", items=items)


# ====== ログイン / ログアウト ======
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("inventory.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT id, role FROM users WHERE username=? AND password=?",
            (username, password)
        )
        user = cur.fetchone()
        conn.close()

        if user:
            session["user_id"] = user[0]
            session["username"] = username
            session["role"] = user[1]
            return redirect("/")
        else:
            error = "ログイン失敗"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ====== 商品追加 / 編集 / 削除 / 在庫更新 ======
@app.route("/add", methods=["POST"])
def add_item():
    name = request.form["name"]
    quantity = int(request.form["quantity"])
    unit = request.form["unit"]

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO items (name, quantity, unit) VALUES (?, ?, ?)",
        (name, quantity, unit)
    )
    conn.commit()
    conn.close()

    add_log("商品追加", name)
    return redirect("/")


@app.route("/edit", methods=["POST"])
def edit_item():
    item_id = request.form["id"]
    name = request.form["name"]
    quantity = int(request.form["quantity"])
    unit = request.form["unit"]

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT name, quantity FROM items WHERE id=?",
        (item_id,)
    )
    old_name, old_qty = cur.fetchone()

    cur.execute(
        "UPDATE items SET name=?, quantity=?, unit=? WHERE id=?",
        (name, quantity, unit, item_id)
    )
    conn.commit()
    conn.close()

    if old_qty != quantity:
        add_log(f"在庫変更 {old_qty} → {quantity}", name)
    else:
        add_log("商品情報編集", name)

    return redirect("/")


@app.route("/update", methods=["POST"])
def update_item():
    item_id = request.form["id"]
    action = request.form["action"]

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT name, quantity FROM items WHERE id=?",
        (item_id,)
    )
    item_name, before_qty = cur.fetchone()

    after_qty = before_qty
    if action == "plus":
        after_qty += 1
    elif action == "minus" and before_qty > 0:
        after_qty -= 1

    cur.execute(
        "UPDATE items SET quantity=? WHERE id=?",
        (after_qty, item_id)
    )
    conn.commit()
    conn.close()

    if before_qty != after_qty:
        add_log(f"在庫変更 {before_qty} → {after_qty}", item_name)

    return redirect("/")


@app.route("/delete", methods=["POST"])
def delete_item():
    if session.get("role") != "admin":
        return "権限がありません", 403

    item_id = request.form["id"]

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()
    cur.execute("SELECT name FROM items WHERE id=?", (item_id,))
    item_name = cur.fetchone()[0]

    cur.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

    add_log("商品削除", item_name)
    return redirect("/")


# ====== 管理者用ユーザー管理 ======
@app.route("/admin/users", methods=["GET", "POST"])
def manage_users():
    if session.get("role") != "admin":
        return "権限がありません", 403

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = "user"

        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, password, role)
        )
        conn.commit()

    cur.execute("SELECT id, username, role FROM users")
    users = cur.fetchall()
    conn.close()

    return render_template("users.html", users=users)


@app.route("/users/delete", methods=["POST"])
def delete_user():
    if session.get("role") != "admin":
        return redirect("/")

    user_id = request.form["user_id"]

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()
    cur.execute("SELECT username, role FROM users WHERE id=?", (user_id,))
    user = cur.fetchone()
    if not user:
        conn.close()
        return redirect("/admin/users")

    username, role = user
    if username == session.get("username"):
        conn.close()
        return redirect("/admin/users")

    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    add_log(f"ユーザー削除（{role}）", username)
    return redirect("/admin/users")


# ====== 管理者用操作ログ ======
@app.route("/admin/logs")
def view_logs():
    if session.get("role") != "admin":
        return "権限がありません", 403

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT user, action, item_name, created_at FROM logs ORDER BY id DESC"
    )
    logs = cur.fetchall()
    conn.close()

    return render_template("logs.html", logs=logs)


# ====== メイン ======
if __name__ == "__main__":
    init_db()
    create_admin()
    app.run(host="0.0.0.0", port=5000, debug=True)
