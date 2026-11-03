import os
import secrets
import hashlib
import sqlite3

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)

from dotenv import load_dotenv
from cryptography.exceptions import InvalidTag

from database import (
    init_db,
    get_connection,
    create_user,
    get_user_by_username,
    get_capability,
    create_owned_capability
)

from security import hash_password, verify_password
from encryption import encrypt_data, decrypt_data


load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY missing from .env")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False
)


@app.before_request
def csrf_protection():
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")

        if not expected or not secrets.compare_digest(
            submitted, expected
        ):
            return "Invalid CSRF token", 403


@app.context_processor
def inject_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return {"csrf_token": session["csrf_token"]}


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    records = []

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, label, ciphertext, nonce
            FROM sensitive_records
            WHERE owner_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    for row in rows:
        try:
            aad = f"user:{user_id}".encode()

            plaintext = decrypt_data(
                row["ciphertext"],
                row["nonce"],
                aad
            )

            records.append({
                "id": row["id"],
                "label": row["label"],
                "content": plaintext
            })

        except InvalidTag:
            app.logger.warning(
                "Record integrity verification failed: %s",
                row["id"]
            )

    return render_template(
        "dashboard.html",
        records=records
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get("password", "")

        if not username or len(username) > 50:
            flash("Username must be 1-50 characters.")
            return redirect(url_for("register"))

        if len(password) < 12:
            flash("Password must be at least 12 characters.")
            return redirect(url_for("register"))

        password_hash = hash_password(password)

        try:
            create_user(username, password_hash)

            flash("Account created successfully.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Username already exists.")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get("password", "")

        user = get_user_by_username(username)

        if user and verify_password(
            user["password_hash"], password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["csrf_token"] = secrets.token_urlsafe(32)

            return redirect(url_for("home"))

        flash("Invalid username or password.")

    return render_template("login.html")


@app.route("/add-record", methods=["POST"])
def add_record():
    if "user_id" not in session:
        return redirect(url_for("login"))

    label = request.form.get("label", "").strip()
    content = request.form.get("content", "").strip()

    user_id = session["user_id"]

    if not label or not content:
        flash("Both fields are required.")
        return redirect(url_for("home"))

    if len(label) > 100 or len(content) > 10000:
        flash("Record exceeds the permitted size.")
        return redirect(url_for("home"))

    aad = f"user:{user_id}".encode()

    ciphertext, nonce = encrypt_data(
        content,
        aad
    )

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sensitive_records
            (owner_id, label, ciphertext, nonce)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, label, ciphertext, nonce)
        )

    flash("Encrypted record saved successfully.")

    return redirect(url_for("home"))


@app.route("/share/<int:record_id>", methods=["POST"])
def share_record(record_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        token.encode()
    ).hexdigest()

    created = create_owned_capability(
        record_id,
        session["user_id"],
        token_hash
    )

    if not created:
        return "Record not found or access denied", 404

    share_url = url_for(
        "shared_record",
        token=token,
        _external=True
    )

    return render_template(
        "share_created.html",
        share_url=share_url
    )


@app.route("/shared/<token>", methods=["GET"])
def shared_record(token):

    token_hash = hashlib.sha256(
        token.encode()
    ).hexdigest()

    record = get_capability(token_hash)

    if not record:
        return "Invalid or expired sharing link", 404

    try:
        aad = f"user:{record['owner_id']}".encode()

        plaintext = decrypt_data(
            record["ciphertext"],
            record["nonce"],
            aad
        )

    except InvalidTag:
        return "Record integrity verification failed", 400

    response = app.make_response(
        render_template(
            "shared_record.html",
            label=record["label"],
            content=plaintext
        )
    )

    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"

    return response


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    init_db()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
