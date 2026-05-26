"""
app.py

Main Flask web application file.

Responsibilities:
1. Display login page
2. Authenticate user from role_login table
3. Create login session
4. Redirect user to role-based dashboard
5. All four role dashboards are wired and active
6. Admin panel API routes (superadmin + admin only):
   - Add user to role_login
   - Add / upsert client to clients table
   - Bulk upsert clients from .xlsx file
   - Download .xlsx client upload template

Login source table:
    role_login

Login fields:
    email, password

Supported roles:
    superadmin, admin, data, operator

Admin Panel access:
    superadmin — can add users of any role
    admin      — can add data and operator users only
"""

from __future__ import annotations

import io
import os
from functools import wraps
from typing import Callable, Optional

import openpyxl
import pymysql
from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    send_file,
    url_for,
    session,
)

from helper import log_info, log_error, log_warning


MODULE_NAME = "app"


# =========================
# Flask App Setup
# =========================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "change-this-secret-key-in-env-file",
)


# =========================
# Constants
# =========================

VALID_ROLES: frozenset[str] = frozenset({"superadmin", "admin", "data", "operator"})
ADMIN_PANEL_ROLES: frozenset[str] = frozenset({"superadmin", "admin"})

# Client columns visible in form and bulk upload (excludes 'server')
CLIENT_FORM_COLUMNS: list[str] = [
    "userId",
    "alias",
    "Broker",
    "algo",
    "Running Type",
    "Operator Name",
    "Category",
    "SubCategory",
    "Acc Type",
]

CLIENT_MAX_LENGTHS: dict[str, int] = {
    "userId": 20,
    "alias": 30,
    "Broker": 20,
    "algo": 10,
    "Running Type": 20,
    "Operator Name": 20,
    "Category": 20,
    "SubCategory": 20,
    "Acc Type": 20,
}

ROLE_LOGIN_MAX_LENGTHS: dict[str, int] = {
    "role": 20,
    "name": 30,
    "ops_name": 20,
    "email": 30,
    "password": 30,
}


# =========================
# MySQL Config
# =========================

def get_mysql_config() -> dict:
    """
    Reads MySQL configuration from environment variables.
    """

    mysql_port_raw = os.getenv("MYSQL_PORT", "3306")

    try:
        mysql_port = int(mysql_port_raw)
    except ValueError as exc:
        raise ValueError("MYSQL_PORT must be a valid integer") from exc

    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": mysql_port,
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "cmp"),
    }


def get_db_connection() -> pymysql.connections.Connection:
    """
    Creates and returns a MySQL database connection.
    Caller is responsible for closing the connection.
    """

    config = get_mysql_config()

    return pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


# =========================
# Auth Helpers
# =========================

def get_user_by_email(email: str) -> Optional[dict]:
    """
    Fetches user row from role_login table by email.

    Args:
        email: login email address

    Returns:
        User dict if found, else None.
    """

    query = """
        SELECT
            role,
            name,
            ops_name,
            email,
            password
        FROM role_login
        WHERE email = %s
        LIMIT 1
    """

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (email,))
            return cursor.fetchone()
    finally:
        connection.close()


def is_valid_role(role: str) -> bool:
    """Returns True if role is in the allowed set."""
    return role in VALID_ROLES


def login_required(view_func: Callable) -> Callable:
    """
    Decorator: redirects unauthenticated users to login page.
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("is_logged_in"):
            log_warning(
                module=MODULE_NAME,
                action="login_required",
                message="Unauthorized access attempt. Redirecting to login.",
                status="FAILED",
            )
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapper


def role_required(required_role: str) -> Callable:
    """
    Decorator: returns HTTP 403 HTML if session role does not match.
    Use for page routes only.
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            current_role = session.get("role")

            if current_role != required_role:
                log_warning(
                    module=MODULE_NAME,
                    action="role_required",
                    message=(
                        f"Access denied. Required: {required_role}, "
                        f"current: {current_role}"
                    ),
                    status="FAILED",
                )
                return render_template(
                    "login.html",
                    error="You do not have permission to access this page.",
                ), 403

            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def redirect_user_by_role(role: str):
    """
    Redirects authenticated user to their role-specific dashboard.
    All four roles are now fully wired.
    """

    if role == "superadmin":
        return redirect(url_for("superadmin_dashboard"))

    if role == "admin":
        return redirect(url_for("admin_dashboard"))

    if role == "data":
        return redirect(url_for("data_dashboard"))

    if role == "operator":
        return redirect(url_for("operator_dashboard"))

    return render_template("login.html", error="Invalid user role.")


# =========================
# Admin Panel Helpers
# =========================

def check_admin_panel_access() -> Optional[tuple]:
    """
    Validates that the current session role has admin panel access.

    Returns:
        None if access is granted.
        JSON error tuple (Response, status_code) if denied.
    """

    if session.get("role") not in ADMIN_PANEL_ROLES:
        return jsonify({"success": False, "error": "Permission denied."}), 403

    return None


def get_allowed_new_roles(current_role: str) -> list[str]:
    """
    Returns the list of roles this user is allowed to assign when adding a new user.

    superadmin: can assign superadmin, admin, data, operator
    admin:      can assign data, operator only
    """

    if current_role == "superadmin":
        return ["superadmin", "admin", "data", "operator"]

    if current_role == "admin":
        return ["data", "operator"]

    return []


def validate_string_field(
    value: str,
    field_name: str,
    max_length: int,
) -> Optional[str]:
    """
    Validates a required string field against max length.

    Returns:
        None if valid.
        Error message string if invalid.
    """

    stripped = str(value).strip()

    if not stripped:
        return f"Field '{field_name}' is required."

    if len(stripped) > max_length:
        return (
            f"Field '{field_name}' exceeds maximum length "
            f"of {max_length} characters."
        )

    return None


# =========================
# DB: User Operations
# =========================

def user_exists_by_ops_name_or_email(
    connection: pymysql.connections.Connection,
    ops_name: str,
    email: str,
) -> Optional[dict]:
    """
    Checks whether a user with the given ops_name or email already exists.

    Returns:
        Matching row dict if found, else None.
    """

    query = """
        SELECT ops_name, email
        FROM role_login
        WHERE ops_name = %s
           OR email = %s
        LIMIT 1
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (ops_name, email))
        return cursor.fetchone()


def insert_role_login_user(
    connection: pymysql.connections.Connection,
    user_data: dict,
) -> None:
    """
    Inserts a new user row into the role_login table.
    """

    query = """
        INSERT INTO role_login (role, name, ops_name, email, password)
        VALUES (%s, %s, %s, %s, %s)
    """

    values = (
        user_data["role"].strip(),
        user_data["name"].strip(),
        user_data["ops_name"].strip(),
        user_data["email"].strip(),
        user_data["password"].strip(),
    )

    with connection.cursor() as cursor:
        cursor.execute(query, values)


# =========================
# DB: Client Operations
# =========================

def client_exists_by_user_id(
    connection: pymysql.connections.Connection,
    user_id: str,
) -> bool:
    """
    Returns True if a client with the given userId already exists.
    """

    query = """
        SELECT userId
        FROM clients
        WHERE userId = %s
        LIMIT 1
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (user_id,))
        return cursor.fetchone() is not None


def insert_client(
    connection: pymysql.connections.Connection,
    client_data: dict,
) -> None:
    """
    Inserts a new client row into the clients table.
    """

    query = """
        INSERT INTO clients
            (userId, alias, Broker, algo, `Running Type`, `Operator Name`,
             Category, SubCategory, `Acc Type`)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    values = (
        str(client_data.get("userId", "")).strip(),
        str(client_data.get("alias", "")).strip(),
        str(client_data.get("Broker", "")).strip(),
        str(client_data.get("algo", "")).strip(),
        str(client_data.get("Running Type", "")).strip(),
        str(client_data.get("Operator Name", "")).strip(),
        str(client_data.get("Category", "")).strip(),
        str(client_data.get("SubCategory", "")).strip(),
        str(client_data.get("Acc Type", "")).strip(),
    )

    with connection.cursor() as cursor:
        cursor.execute(query, values)


def update_client(
    connection: pymysql.connections.Connection,
    client_data: dict,
) -> None:
    """
    Updates an existing client row identified by userId.
    """

    query = """
        UPDATE clients
        SET
            alias          = %s,
            Broker         = %s,
            algo           = %s,
            `Running Type`   = %s,
            `Operator Name`  = %s,
            Category       = %s,
            SubCategory    = %s,
            `Acc Type`       = %s
        WHERE userId = %s
    """

    values = (
        str(client_data.get("alias", "")).strip(),
        str(client_data.get("Broker", "")).strip(),
        str(client_data.get("algo", "")).strip(),
        str(client_data.get("Running Type", "")).strip(),
        str(client_data.get("Operator Name", "")).strip(),
        str(client_data.get("Category", "")).strip(),
        str(client_data.get("SubCategory", "")).strip(),
        str(client_data.get("Acc Type", "")).strip(),
        str(client_data.get("userId", "")).strip(),
    )

    with connection.cursor() as cursor:
        cursor.execute(query, values)


def upsert_client(
    connection: pymysql.connections.Connection,
    client_data: dict,
) -> str:
    """
    Inserts or updates a client by userId.

    Returns:
        "inserted" — new client was created.
        "updated"  — existing client was updated.
    """

    user_id = str(client_data.get("userId", "")).strip()

    if client_exists_by_user_id(connection, user_id):
        update_client(connection, client_data)
        return "updated"

    insert_client(connection, client_data)
    return "inserted"


def validate_client_data(client_data: dict) -> Optional[str]:
    """
    Validates all required client fields against schema constraints.

    Returns:
        None if all fields are valid.
        First encountered error message string if any field is invalid.
    """

    for field, max_len in CLIENT_MAX_LENGTHS.items():
        error_msg = validate_string_field(
            value=str(client_data.get(field, "")),
            field_name=field,
            max_length=max_len,
        )
        if error_msg:
            return error_msg

    return None


# =========================
# Routes: Public
# =========================

@app.route("/", methods=["GET"])
def index():
    """
    Root route.
    Redirects logged-in users to their dashboard, otherwise shows login.
    """

    if session.get("is_logged_in"):
        return redirect_user_by_role(session.get("role", ""))

    log_info(
        module=MODULE_NAME,
        action="index",
        message="Login page requested from root URL",
        status="SUCCESS",
    )

    return render_template("login.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Login route.

    GET:  Show login page (redirect to dashboard if already logged in).
    POST: Authenticate email/password against role_login table.
    """

    if request.method == "GET":
        if session.get("is_logged_in"):
            return redirect_user_by_role(session.get("role", ""))

        log_info(
            module=MODULE_NAME,
            action="login_get",
            message="Login page requested",
            status="SUCCESS",
        )

        return render_template("login.html")

    try:
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        log_info(
            module=MODULE_NAME,
            action="login_post",
            message=f"Login attempt for email: {email}",
            status="STARTED",
        )

        if not email or not password:
            log_warning(
                module=MODULE_NAME,
                action="login_validation",
                message="Email or password missing in login attempt",
                status="FAILED",
            )
            return render_template(
                "login.html",
                error="Email and password are required.",
            )

        user = get_user_by_email(email)

        if user is None:
            log_warning(
                module=MODULE_NAME,
                action="login_authentication",
                message=f"Login failed. Email not found: {email}",
                status="FAILED",
            )
            return render_template("login.html", error="Invalid email or password.")

        existing_password = str(user.get("password", "")).strip()

        if password != existing_password:
            log_warning(
                module=MODULE_NAME,
                action="login_authentication",
                message=f"Login failed. Password mismatch for: {email}",
                status="FAILED",
            )
            return render_template("login.html", error="Invalid email or password.")

        role = str(user.get("role", "")).strip().lower()

        if not is_valid_role(role):
            log_warning(
                module=MODULE_NAME,
                action="login_role_validation",
                message=f"Invalid role '{role}' for email: {email}",
                status="FAILED",
            )
            return render_template(
                "login.html",
                error="Invalid role assigned to this user.",
            )

        session.clear()
        session["is_logged_in"] = True
        session["role"] = role
        session["name"] = str(user.get("name", "")).strip()
        session["ops_name"] = str(user.get("ops_name", "")).strip()
        session["email"] = str(user.get("email", "")).strip()

        log_info(
            module=MODULE_NAME,
            action="login_authentication",
            message=f"Login successful for email: {email}, role: {role}",
            status="SUCCESS",
        )

        return redirect_user_by_role(role)

    except Exception as exc:
        log_error(
            module=MODULE_NAME,
            action="login_post",
            message="Login request failed with unexpected error",
            error=exc,
            status="FAILED",
        )
        return render_template("login.html", error="Something went wrong. Please try again.")


@app.route("/logout", methods=["GET"])
def logout():
    """
    Clears session and redirects to login page.
    """

    user_email = session.get("email", "unknown")
    session.clear()

    log_info(
        module=MODULE_NAME,
        action="logout",
        message=f"User logged out: {user_email}",
        status="SUCCESS",
    )

    return redirect(url_for("login"))


# =========================
# Routes: Dashboards
# =========================

@app.route("/superadmin/dashboard", methods=["GET"])
@login_required
@role_required("superadmin")
def superadmin_dashboard():
    """Superadmin dashboard page."""

    log_info(
        module=MODULE_NAME,
        action="superadmin_dashboard",
        message="Superadmin dashboard requested",
        status="SUCCESS",
    )

    return render_template(
        "superadmin/dashboard.html",
        name=session.get("name"),
        ops_name=session.get("ops_name"),
        email=session.get("email"),
        role=session.get("role"),
    )


@app.route("/admin/dashboard", methods=["GET"])
@login_required
@role_required("admin")
def admin_dashboard():
    """Admin dashboard page."""

    log_info(
        module=MODULE_NAME,
        action="admin_dashboard",
        message="Admin dashboard requested",
        status="SUCCESS",
    )

    return render_template(
        "admin/dashboard.html",
        name=session.get("name"),
        ops_name=session.get("ops_name"),
        email=session.get("email"),
        role=session.get("role"),
    )


@app.route("/data/dashboard", methods=["GET"])
@login_required
@role_required("data")
def data_dashboard():
    """Data dashboard page."""

    log_info(
        module=MODULE_NAME,
        action="data_dashboard",
        message="Data dashboard requested",
        status="SUCCESS",
    )

    return render_template(
        "data/dashboard.html",
        name=session.get("name"),
        ops_name=session.get("ops_name"),
        email=session.get("email"),
        role=session.get("role"),
    )


@app.route("/operator/dashboard", methods=["GET"])
@login_required
@role_required("operator")
def operator_dashboard():
    """Operator dashboard page."""

    log_info(
        module=MODULE_NAME,
        action="operator_dashboard",
        message="Operator dashboard requested",
        status="SUCCESS",
    )

    return render_template(
        "operator/dashboard.html",
        name=session.get("name"),
        ops_name=session.get("ops_name"),
        email=session.get("email"),
        role=session.get("role"),
    )


# =========================
# Routes: Admin Panel API
# =========================

@app.route("/admin-panel/add-user", methods=["POST"])
@login_required
def add_user():
    """
    Inserts a new user into role_login table.

    Access: superadmin, admin only.
    superadmin can assign any role.
    admin can only assign: data, operator.

    Form fields:
        role, name, ops_name, email, password

    Returns:
        JSON — {"success": True/False, "message"/"error": str}
    """

    access_error = check_admin_panel_access()
    if access_error:
        return access_error

    current_role = session.get("role", "")

    try:
        new_role    = str(request.form.get("role", "")).strip().lower()
        name        = str(request.form.get("name", "")).strip()
        ops_name    = str(request.form.get("ops_name", "")).strip()
        email       = str(request.form.get("email", "")).strip()
        password    = str(request.form.get("password", "")).strip()

        log_info(
            module=MODULE_NAME,
            action="add_user",
            message=(
                f"Add user request by {session.get('email')} "
                f"for ops_name: {ops_name}, role: {new_role}"
            ),
            status="STARTED",
        )

        # Role field presence check
        if not new_role:
            return jsonify({"success": False, "error": "Role is required."}), 400

        # Role assignment permission check (backend guard, not just frontend)
        allowed_new_roles = get_allowed_new_roles(current_role)

        if new_role not in allowed_new_roles:
            log_warning(
                module=MODULE_NAME,
                action="add_user",
                message=(
                    f"Unauthorized role assignment by {session.get('email')}: "
                    f"tried to assign '{new_role}'"
                ),
                status="FAILED",
            )
            return jsonify({
                "success": False,
                "error": f"You are not permitted to assign the role '{new_role}'.",
            }), 403

        # Validate remaining fields
        fields_to_validate = [
            (name,     "name",     ROLE_LOGIN_MAX_LENGTHS["name"]),
            (ops_name, "ops_name", ROLE_LOGIN_MAX_LENGTHS["ops_name"]),
            (email,    "email",    ROLE_LOGIN_MAX_LENGTHS["email"]),
            (password, "password", ROLE_LOGIN_MAX_LENGTHS["password"]),
        ]

        for value, field_name, max_len in fields_to_validate:
            error_msg = validate_string_field(value, field_name, max_len)
            if error_msg:
                return jsonify({"success": False, "error": error_msg}), 400

        # Duplicate check
        connection = get_db_connection()

        try:
            duplicate = user_exists_by_ops_name_or_email(connection, ops_name, email)

            if duplicate:
                conflict_field = (
                    "ops_name" if duplicate.get("ops_name") == ops_name else "email"
                )
                return jsonify({
                    "success": False,
                    "error": f"A user with this {conflict_field} already exists.",
                }), 409

            insert_role_login_user(connection, {
                "role": new_role,
                "name": name,
                "ops_name": ops_name,
                "email": email,
                "password": password,
            })

        finally:
            connection.close()

        log_info(
            module=MODULE_NAME,
            action="add_user",
            message=f"User '{ops_name}' added by {session.get('email')}, role: {new_role}",
            status="SUCCESS",
        )

        return jsonify({
            "success": True,
            "message": f"User '{name}' added successfully with role '{new_role}'.",
        }), 201

    except Exception as exc:
        log_error(
            module=MODULE_NAME,
            action="add_user",
            message="Add user request failed",
            error=exc,
            status="FAILED",
        )
        return jsonify({"success": False, "error": "Something went wrong. Please try again."}), 500


@app.route("/admin-panel/add-client", methods=["POST"])
@login_required
def add_client():
    """
    Inserts or updates a single client in the clients table.
    Upsert rule: if userId exists → UPDATE, else → INSERT.

    Access: superadmin, admin only.

    Form fields:
        userId, alias, Broker, algo, Running Type,
        Operator Name, Category, SubCategory, Acc Type

    Returns:
        JSON — {"success": True/False, "action": "inserted"/"updated", "message"/"error": str}
    """

    access_error = check_admin_panel_access()
    if access_error:
        return access_error

    try:
        client_data: dict = {
            col: str(request.form.get(col, "")).strip()
            for col in CLIENT_FORM_COLUMNS
        }

        log_info(
            module=MODULE_NAME,
            action="add_client",
            message=(
                f"Add client request by {session.get('email')} "
                f"for userId: {client_data.get('userId', '')}"
            ),
            status="STARTED",
        )

        validation_error = validate_client_data(client_data)
        if validation_error:
            return jsonify({"success": False, "error": validation_error}), 400

        connection = get_db_connection()

        try:
            action = upsert_client(connection, client_data)
        finally:
            connection.close()

        action_word = "added" if action == "inserted" else "updated"

        log_info(
            module=MODULE_NAME,
            action="add_client",
            message=(
                f"Client '{client_data['userId']}' {action_word} "
                f"by {session.get('email')}"
            ),
            status="SUCCESS",
        )

        return jsonify({
            "success": True,
            "action": action,
            "message": f"Client '{client_data['userId']}' {action_word} successfully.",
        }), 200

    except Exception as exc:
        log_error(
            module=MODULE_NAME,
            action="add_client",
            message="Add client request failed",
            error=exc,
            status="FAILED",
        )
        return jsonify({"success": False, "error": "Something went wrong. Please try again."}), 500


@app.route("/admin-panel/bulk-upload-clients", methods=["POST"])
@login_required
def bulk_upload_clients():
    """
    Bulk upserts clients from an uploaded .xlsx file.

    Access: superadmin, admin only.

    Expected .xlsx columns (header row, any order):
        userId, alias, Broker, algo, Running Type, Operator Name,
        Category, SubCategory, Acc Type

    Upsert rule per row: if userId exists → UPDATE, else → INSERT.
    Rows with validation errors are skipped and reported.

    Returns:
        JSON — {
            "success": True/False,
            "inserted": int,
            "updated": int,
            "errors": [{"row": int, "userId": str, "error": str}],
            "message": str
        }
    """

    access_error = check_admin_panel_access()
    if access_error:
        return access_error

    try:
        uploaded_file = request.files.get("file")

        if not uploaded_file or not uploaded_file.filename:
            return jsonify({"success": False, "error": "No file uploaded."}), 400

        if not uploaded_file.filename.lower().endswith(".xlsx"):
            return jsonify({"success": False, "error": "Only .xlsx files are accepted."}), 400

        log_info(
            module=MODULE_NAME,
            action="bulk_upload_clients",
            message=(
                f"Bulk upload started by {session.get('email')}, "
                f"file: {uploaded_file.filename}"
            ),
            status="STARTED",
        )

        file_bytes = uploaded_file.read()

        try:
            workbook = openpyxl.load_workbook(
                io.BytesIO(file_bytes),
                read_only=True,
                data_only=True,
            )
        except Exception:
            return jsonify({"success": False, "error": "Could not read the uploaded file. Ensure it is a valid .xlsx file."}), 400

        worksheet = workbook.active
        rows = list(worksheet.iter_rows(values_only=True))
        workbook.close()

        if not rows:
            return jsonify({"success": False, "error": "Uploaded file is empty."}), 400

        # Parse header row
        raw_headers = [
            str(h).strip() if h is not None else ""
            for h in rows[0]
        ]

        # Validate all required columns are present
        missing_columns = [
            col for col in CLIENT_FORM_COLUMNS
            if col not in raw_headers
        ]

        if missing_columns:
            return jsonify({
                "success": False,
                "error": f"Missing required columns in file: {', '.join(missing_columns)}",
            }), 400

        data_rows = rows[1:]

        if not data_rows:
            return jsonify({"success": False, "error": "No data rows found in file."}), 400

        inserted_count = 0
        updated_count  = 0
        error_rows: list[dict] = []

        connection = get_db_connection()

        try:
            for row_index, row in enumerate(data_rows, start=2):
                row_values = [
                    str(v).strip() if v is not None else ""
                    for v in row
                ]

                row_dict    = dict(zip(raw_headers, row_values))
                client_data = {col: row_dict.get(col, "") for col in CLIENT_FORM_COLUMNS}

                validation_error = validate_client_data(client_data)

                if validation_error:
                    error_rows.append({
                        "row": row_index,
                        "userId": client_data.get("userId", ""),
                        "error": validation_error,
                    })
                    continue

                action = upsert_client(connection, client_data)

                if action == "inserted":
                    inserted_count += 1
                else:
                    updated_count += 1

        finally:
            connection.close()

        log_info(
            module=MODULE_NAME,
            action="bulk_upload_clients",
            message=(
                f"Bulk upload by {session.get('email')} complete: "
                f"inserted={inserted_count}, updated={updated_count}, "
                f"errors={len(error_rows)}"
            ),
            status="SUCCESS",
        )

        return jsonify({
            "success": True,
            "inserted": inserted_count,
            "updated": updated_count,
            "errors": error_rows,
            "message": (
                f"Bulk upload complete — {inserted_count} inserted, "
                f"{updated_count} updated"
                + (f", {len(error_rows)} row(s) skipped due to errors." if error_rows else ".")
            ),
        }), 200

    except Exception as exc:
        log_error(
            module=MODULE_NAME,
            action="bulk_upload_clients",
            message="Bulk upload failed",
            error=exc,
            status="FAILED",
        )
        return jsonify({"success": False, "error": "Something went wrong. Please try again."}), 500


@app.route("/admin-panel/download-client-template", methods=["GET"])
@login_required
def download_client_template():
    """
    Generates and serves an .xlsx template file for bulk client upload.
    The template contains only the header row with the required column names.

    Access: superadmin, admin only.
    """

    access_error = check_admin_panel_access()
    if access_error:
        return access_error

    try:
        workbook  = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = "Clients"
        worksheet.append(CLIENT_FORM_COLUMNS)

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        log_info(
            module=MODULE_NAME,
            action="download_client_template",
            message=f"Client upload template downloaded by {session.get('email')}",
            status="SUCCESS",
        )

        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="client_upload_template.xlsx",
        )

    except Exception as exc:
        log_error(
            module=MODULE_NAME,
            action="download_client_template",
            message="Client template generation failed",
            error=exc,
            status="FAILED",
        )
        return jsonify({"success": False, "error": "Could not generate template."}), 500


# =========================
# Error Handlers
# =========================

@app.errorhandler(404)
def page_not_found(error):
    """Handles unknown routes."""

    log_error(
        module=MODULE_NAME,
        action="404_error",
        message="Page not found",
        error=error,
        status="FAILED",
    )

    return render_template("login.html", error="Page not found."), 404


@app.errorhandler(500)
def internal_server_error(error):
    """Handles internal server errors."""

    log_error(
        module=MODULE_NAME,
        action="500_error",
        message="Internal server error",
        error=error,
        status="FAILED",
    )

    return render_template("login.html", error="Internal server error."), 500
