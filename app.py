import os
from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret_key_for_inventory_app"

print("DB path:", os.path.abspath("inventory.db"))


def add_log(action, item_name):
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
    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()

    # items
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            quantity INTEGER,
            unit TEXT
        )
    """)

    # users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    # 🔴 これが不足していた
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


@app.route("/")
def index():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name, quantity, unit FROM items")
    items = cur.fetchall()
    conn.close()

    return render_template("index.html", items=items)


if __name__ == "__main__":
    init_db()
    app.run()

@app.route("/add", methods=["POST"])
def add_item():
    name = request.form["name"]
    quantity = request.form["quantity"]
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

@app.route("/update", methods=["POST"])
def update_item():
    item_id = request.form["id"]
    action = request.form["action"]

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()

    # ① 変更前の情報を取得
    cur.execute(
        "SELECT name, quantity FROM items WHERE id=?",
        (item_id,)
    )
    item_name, before_qty = cur.fetchone()

    # ② 数量を変更
    if action == "plus":
        after_qty = before_qty + 1
    elif action == "minus" and before_qty > 0:
        after_qty = before_qty - 1
    else:
        conn.close()
        return redirect("/")

    cur.execute(
        "UPDATE items SET quantity=? WHERE id=?",
        (after_qty, item_id)
    )

    conn.commit()
    conn.close()

    # ③ 差分付きログ
    add_log(
        f"在庫変更 {before_qty} → {after_qty}",
        item_name
    )

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

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("inventory.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, role FROM users WHERE username=? AND password=?",
            (username, password)
        )
        user = cur.fetchone()
        conn.close()

        if user:
            session["user_id"] = user[0]
            session["username"] = user[1]
            session["role"] = user[2]
            return redirect("/")
        else:
            return render_template("login.html", error="ログイン失敗")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

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

@app.route("/edit", methods=["POST"])
def edit_item():
    item_id = request.form["id"]
    name = request.form["name"]
    quantity = int(request.form["quantity"])
    unit = request.form["unit"]

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()

    # 変更前取得
    cur.execute(
        "SELECT name, quantity FROM items WHERE id=?",
        (item_id,)
    )
    old_name, old_qty = cur.fetchone()

    # 更新
    cur.execute(
        "UPDATE items SET name=?, quantity=?, unit=? WHERE id=?",
        (name, quantity, unit, item_id)
    )

    conn.commit()
    conn.close()

    # ログ（在庫変動があった場合のみ差分表示）
    if old_qty != quantity:
        add_log(
            f"在庫変更 {old_qty} → {quantity}",
            name
        )
    else:
        add_log("商品情報編集", name)

    return redirect("/")

@app.route("/users/delete", methods=["POST"])
def delete_user():
    # 管理者チェック
    if session.get("role") != "admin":
        return redirect("/")

    user_id = request.form["user_id"]

    conn = sqlite3.connect("inventory.db")
    cur = conn.cursor()

    # 削除対象の情報取得
    cur.execute(
        "SELECT username, role FROM users WHERE id=?",
        (user_id,)
    )
    user = cur.fetchone()

    if not user:
        conn.close()
        return redirect("/admin/users")

    username, role = user

    # 自分自身は削除不可（二重チェック）
    if username == session.get("username"):
        conn.close()
        return redirect("/admin/users")

    # 削除
    cur.execute(
        "DELETE FROM users WHERE id=?",
        (user_id,)
    )

    conn.commit()
    conn.close()

    # ログ
    add_log(
        f"ユーザー削除（{role}）",
        username
    )

    return redirect("/admin/users")

# ⚠️ これが必ず「一番最後」
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)



