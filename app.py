"""
app.py

Main Flask web application file.

Current responsibility:
1. Display login page
2. Authenticate user from role_login table
3. Create login session
4. Redirect user to role-based dashboard
5. For now, only superadmin dashboard is implemented

Login source table:
    role_login

Login fields:
    email
    password

Supported roles:
    superadmin
    admin
    data
    operator
"""

from __future__ import annotations

import os
from functools import wraps
from typing import Callable, Optional

import pymysql
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
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
    Creates MySQL database connection.
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
    Fetch user from role_login table using email.

    Args:
        email: user login email

    Returns:
        user row if found, else None
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
            user = cursor.fetchone()

        return user

    finally:
        connection.close()


def is_valid_role(role: str) -> bool:
    """
    Checks allowed application roles.
    """

    allowed_roles = {"superadmin", "admin", "data", "operator"}
    return role in allowed_roles


def login_required(view_func: Callable) -> Callable:
    """
    Decorator to protect logged-in pages.
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("is_logged_in"):
            log_warning(
                module=MODULE_NAME,
                action="login_required",
                message="Unauthorized access attempt. Redirecting to login page.",
                status="FAILED",
            )

            return redirect(url_for("login"))

        return view_func(*args, **kwargs)

    return wrapper


def role_required(required_role: str) -> Callable:
    """
    Decorator to protect role-based pages.
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
                        f"Access denied. Required role: {required_role}, "
                        f"current role: {current_role}"
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
    Redirects user to dashboard based on role.
    """

    if role == "superadmin":
        return redirect(url_for("superadmin_dashboard"))

    if role == "admin":
        return render_template(
            "login.html",
            error="Admin dashboard is not created yet.",
        )

    if role == "data":
        return render_template(
            "login.html",
            error="Data dashboard is not created yet.",
        )

    if role == "operator":
        return render_template(
            "login.html",
            error="Operator dashboard is not created yet.",
        )

    return render_template(
        "login.html",
        error="Invalid user role.",
    )


# =========================
# Routes
# =========================

@app.route("/", methods=["GET"])
def index():
    """
    Root route.

    If user is already logged in, redirect to role dashboard.
    Otherwise show login page.
    """

    if session.get("is_logged_in"):
        role = session.get("role", "")
        return redirect_user_by_role(role)

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

    GET:
        Display login page.

    POST:
        Check email and password from role_login table.
    """

    if request.method == "GET":
        if session.get("is_logged_in"):
            role = session.get("role", "")
            return redirect_user_by_role(role)

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
            message=f"Login attempt received for email: {email}",
            status="STARTED",
        )

        if not email or not password:
            log_warning(
                module=MODULE_NAME,
                action="login_validation",
                message="Email or password missing",
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

            return render_template(
                "login.html",
                error="Invalid email or password.",
            )

        existing_password = str(user.get("password", "")).strip()
        entered_password = str(password).strip()

        if entered_password != existing_password:
            log_warning(
                module=MODULE_NAME,
                action="login_authentication",
                message=f"Login failed. Password mismatch for email: {email}",
                status="FAILED",
            )

            return render_template(
                "login.html",
                error="Invalid email or password.",
            )

        role = str(user.get("role", "")).strip().lower()

        if not is_valid_role(role):
            log_warning(
                module=MODULE_NAME,
                action="login_role_validation",
                message=f"Invalid role found for email {email}: {role}",
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
            message="Login request failed",
            error=exc,
            status="FAILED",
        )

        return render_template(
            "login.html",
            error="Something went wrong. Please try again.",
        )


@app.route("/superadmin/dashboard", methods=["GET"])
@login_required
@role_required("superadmin")
def superadmin_dashboard():
    """
    Superadmin dashboard page.
    """

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


@app.route("/logout", methods=["GET"])
def logout():
    """
    Clears user session and redirects to login page.
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
# Error Handlers
# =========================

@app.errorhandler(404)
def page_not_found(error):
    """
    Handles unknown routes.
    """

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
    """
    Handles server errors.
    """

    log_error(
        module=MODULE_NAME,
        action="500_error",
        message="Internal server error",
        error=error,
        status="FAILED",
    )

    return render_template(
        "login.html",
        error="Internal server error.",
    ), 500