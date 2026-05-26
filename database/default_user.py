"""
database/default_user.py

Responsible for inserting default users into required tables.

Current responsibility:
1. Add default superadmin user into role_login table
2. Skip insert if the user already exists by ops_name or email
3. Log all actions to terminal and logs/logs.csv

Run:
    python database/default_user.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pymysql


ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from helper import log_info, log_error, log_warning
from database.creation import (
    load_environment,
    get_mysql_config,
    validate_mysql_config,
    get_mysql_connection_with_database,
)


MODULE_NAME = "database.default_user"


DEFAULT_SUPERADMIN_USER = {
    "role": "superadmin",
    "name": "superadmin",
    "ops_name": "superadmin",
    "email": "superadmin@megaserve.tech",
    "password": "sadmin2331",
}


def validate_default_user_payload(user_data: dict) -> None:
    """
    Validates default user data before inserting.

    Current role_login schema:
        role     VARCHAR(20)
        name     VARCHAR(30)
        ops_name VARCHAR(20)
        email    VARCHAR(30)
        password VARCHAR(30)
    """

    required_fields = ["role", "name", "ops_name", "email", "password"]

    missing_fields = [
        field
        for field in required_fields
        if field not in user_data or str(user_data[field]).strip() == ""
    ]

    if missing_fields:
        raise ValueError(
            f"Missing required default user fields: {', '.join(missing_fields)}"
        )

    max_lengths = {
        "role": 20,
        "name": 30,
        "ops_name": 20,
        "email": 30,
        "password": 30,
    }

    for field, max_length in max_lengths.items():
        value = str(user_data[field]).strip()

        if len(value) > max_length:
            raise ValueError(
                f"Field '{field}' exceeds max length {max_length}. Current length: {len(value)}"
            )


def default_user_exists(
    connection: pymysql.connections.Connection,
    ops_name: str,
    email: str,
) -> bool:
    """
    Checks whether default user already exists by ops_name or email.
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
        result: Optional[dict] = cursor.fetchone()

    return result is not None


def insert_default_user(
    connection: pymysql.connections.Connection,
    user_data: dict,
) -> None:
    """
    Inserts default user into role_login table.
    """

    query = """
        INSERT INTO role_login
            (role, name, ops_name, email, password)
        VALUES
            (%s, %s, %s, %s, %s)
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


def seed_default_superadmin_user() -> None:
    """
    Adds default superadmin user if it does not already exist.
    """

    log_info(
        module=MODULE_NAME,
        action="seed_default_superadmin_user",
        message="Starting default superadmin user seed process",
        status="STARTED",
    )

    try:
        load_environment()

        config = get_mysql_config()
        validate_mysql_config(config)

        validate_default_user_payload(DEFAULT_SUPERADMIN_USER)

        connection = get_mysql_connection_with_database(config)

        try:
            log_info(
                module=MODULE_NAME,
                action="mysql_connection",
                message=f"Connected to database '{config['database']}' successfully",
                status="SUCCESS",
            )

            exists = default_user_exists(
                connection=connection,
                ops_name=DEFAULT_SUPERADMIN_USER["ops_name"],
                email=DEFAULT_SUPERADMIN_USER["email"],
            )

            if exists:
                log_warning(
                    module=MODULE_NAME,
                    action="default_user_check",
                    message=(
                        "Default superadmin user already exists. "
                        "No insert required."
                    ),
                    status="SKIPPED",
                )
                return

            insert_default_user(
                connection=connection,
                user_data=DEFAULT_SUPERADMIN_USER,
            )

            log_info(
                module=MODULE_NAME,
                action="insert_default_user",
                message=(
                    "Default superadmin user inserted successfully "
                    f"with email '{DEFAULT_SUPERADMIN_USER['email']}'"
                ),
                status="SUCCESS",
            )

        finally:
            connection.close()

            log_info(
                module=MODULE_NAME,
                action="mysql_connection",
                message="Database connection closed",
                status="SUCCESS",
            )

    except Exception as exc:
        log_error(
            module=MODULE_NAME,
            action="seed_default_superadmin_user",
            message="Default superadmin user seed process failed",
            error=exc,
            status="FAILED",
        )
        raise


if __name__ == "__main__":
    seed_default_superadmin_user()