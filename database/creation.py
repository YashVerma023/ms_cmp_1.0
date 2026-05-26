"""
database/creation.py

Responsible for:
1. Connecting to MySQL server
2. Checking whether database `cmp` exists
3. Creating database if it does not exist
4. Checking whether `role_login` table exists
5. Creating `role_login` table if it does not exist
6. Syncing `role_login` table schema:
   - Add missing columns
   - Modify columns with wrong datatype
   - Drop extra columns
7. Logging all operations to terminal and logs/logs.csv

Run:
    python database/creation.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import pymysql
from dotenv import load_dotenv


# Allow importing helper.py from root directory
ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from helper import log_info, log_error, log_warning, log_startup_banner


MODULE_NAME = "database.creation"


ROLE_LOGIN_SCHEMA = {
    "role": "VARCHAR(20)",
    "name": "VARCHAR(30)",
    "ops_name": "VARCHAR(20)",
    "email": "VARCHAR(30)",
    "password": "VARCHAR(30)",
}


def load_environment() -> None:
    """
    Loads environment variables from .env file.
    """

    env_path = ROOT_DIR / ".env"

    if env_path.exists():
        load_dotenv(env_path)

        log_info(
            module=MODULE_NAME,
            action="load_environment",
            message=".env file loaded successfully",
            status="SUCCESS",
        )
    else:
        log_warning(
            module=MODULE_NAME,
            action="load_environment",
            message=".env file not found. Falling back to system environment variables.",
            status="WARNING",
        )


def get_mysql_config() -> dict:
    """
    Reads MySQL connection config from environment variables.

    Required:
        MYSQL_HOST
        MYSQL_PORT
        MYSQL_USER
        MYSQL_PASSWORD

    Optional:
        MYSQL_DATABASE - defaults to cmp
    """

    mysql_host = os.getenv("MYSQL_HOST", "localhost")
    mysql_port_raw = os.getenv("MYSQL_PORT", "3306")
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_password = os.getenv("MYSQL_PASSWORD", "")
    mysql_database = os.getenv("MYSQL_DATABASE", "cmp")

    try:
        mysql_port = int(mysql_port_raw)
    except ValueError as exc:
        raise ValueError("MYSQL_PORT must be a valid integer") from exc

    return {
        "host": mysql_host,
        "port": mysql_port,
        "user": mysql_user,
        "password": mysql_password,
        "database": mysql_database,
    }


def validate_mysql_config(config: dict) -> None:
    """
    Validates MySQL configuration before connecting.
    """

    required_fields = ["host", "port", "user", "database"]

    missing_fields = [
        field
        for field in required_fields
        if config.get(field) is None or str(config.get(field)).strip() == ""
    ]

    if missing_fields:
        raise ValueError(
            f"Missing required MySQL configuration fields: {', '.join(missing_fields)}"
        )

    if not isinstance(config["port"], int):
        raise TypeError("MYSQL_PORT must be an integer")

    if config["database"] != "cmp":
        log_warning(
            module=MODULE_NAME,
            action="validate_mysql_config",
            message=f"MYSQL_DATABASE is set to '{config['database']}', expected database is 'cmp'",
            status="WARNING",
        )


def validate_mysql_identifier(identifier: str) -> None:
    """
    Validates database, table, and column names.

    Allows:
    - letters
    - numbers
    - underscore

    This prevents unsafe SQL identifier injection.
    """

    if not identifier:
        raise ValueError("MySQL identifier cannot be empty")

    if not identifier.replace("_", "").isalnum():
        raise ValueError(
            f"Invalid MySQL identifier '{identifier}'. Only letters, numbers, and underscores are allowed."
        )


def get_mysql_connection_without_database(
    config: dict,
) -> pymysql.connections.Connection:
    """
    Creates MySQL server connection without selecting database.

    Required because database may not exist yet.
    """

    return pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def get_mysql_connection_with_database(
    config: dict,
) -> pymysql.connections.Connection:
    """
    Creates MySQL connection after database exists.
    """

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


def database_exists(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> bool:
    """
    Checks whether database exists.
    """

    query = """
        SELECT SCHEMA_NAME
        FROM INFORMATION_SCHEMA.SCHEMATA
        WHERE SCHEMA_NAME = %s
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (database_name,))
        result: Optional[dict] = cursor.fetchone()

    return result is not None


def create_database(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    """
    Creates database with utf8mb4 charset.
    """

    validate_mysql_identifier(database_name)

    query = f"""
        CREATE DATABASE `{database_name}`
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci
    """

    with connection.cursor() as cursor:
        cursor.execute(query)


def table_exists(
    connection: pymysql.connections.Connection,
    database_name: str,
    table_name: str,
) -> bool:
    """
    Checks whether table exists inside selected database.
    """

    query = """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (database_name, table_name))
        result: Optional[dict] = cursor.fetchone()

    return result is not None


def create_role_login_table(connection: pymysql.connections.Connection) -> None:
    """
    Creates role_login table with the required schema.
    """

    query = """
        CREATE TABLE role_login (
            role VARCHAR(20),
            name VARCHAR(30),
            ops_name VARCHAR(20),
            email VARCHAR(30),
            password VARCHAR(30)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """

    with connection.cursor() as cursor:
        cursor.execute(query)


def get_existing_columns(
    connection: pymysql.connections.Connection,
    database_name: str,
    table_name: str,
) -> dict:
    """
    Returns current table columns with their full datatype.

    Example output:
        {
            "role": "varchar(20)",
            "name": "varchar(30)"
        }
    """

    query = """
        SELECT COLUMN_NAME, COLUMN_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (database_name, table_name))
        rows = cursor.fetchall()

    return {
        row["COLUMN_NAME"]: row["COLUMN_TYPE"].upper()
        for row in rows
    }


def add_missing_column(
    connection: pymysql.connections.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    """
    Adds a missing column to table.
    """

    validate_mysql_identifier(table_name)
    validate_mysql_identifier(column_name)

    query = f"""
        ALTER TABLE `{table_name}`
        ADD COLUMN `{column_name}` {column_type}
    """

    with connection.cursor() as cursor:
        cursor.execute(query)


def modify_existing_column(
    connection: pymysql.connections.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    """
    Modifies existing column datatype.
    """

    validate_mysql_identifier(table_name)
    validate_mysql_identifier(column_name)

    query = f"""
        ALTER TABLE `{table_name}`
        MODIFY COLUMN `{column_name}` {column_type}
    """

    with connection.cursor() as cursor:
        cursor.execute(query)


def drop_extra_column(
    connection: pymysql.connections.Connection,
    table_name: str,
    column_name: str,
) -> None:
    """
    Drops an extra column from table.
    """

    validate_mysql_identifier(table_name)
    validate_mysql_identifier(column_name)

    query = f"""
        ALTER TABLE `{table_name}`
        DROP COLUMN `{column_name}`
    """

    with connection.cursor() as cursor:
        cursor.execute(query)


def sync_role_login_schema(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    """
    Synchronizes role_login table with required schema.

    Actions:
    1. Add missing columns
    2. Modify columns with wrong datatype
    3. Drop extra columns
    """

    table_name = "role_login"

    log_info(
        module=MODULE_NAME,
        action="sync_role_login_schema",
        message="Starting role_login table schema sync",
        status="STARTED",
    )

    existing_columns = get_existing_columns(
        connection=connection,
        database_name=database_name,
        table_name=table_name,
    )

    required_columns = ROLE_LOGIN_SCHEMA

    # Add missing columns and modify wrong datatypes
    for column_name, required_type in required_columns.items():
        existing_type = existing_columns.get(column_name)

        if existing_type is None:
            add_missing_column(
                connection=connection,
                table_name=table_name,
                column_name=column_name,
                column_type=required_type,
            )

            log_info(
                module=MODULE_NAME,
                action="add_missing_column",
                message=f"Added missing column '{column_name}' with datatype '{required_type}'",
                status="SUCCESS",
            )

        elif existing_type != required_type.upper():
            modify_existing_column(
                connection=connection,
                table_name=table_name,
                column_name=column_name,
                column_type=required_type,
            )

            log_info(
                module=MODULE_NAME,
                action="modify_existing_column",
                message=f"Modified column '{column_name}' from '{existing_type}' to '{required_type}'",
                status="SUCCESS",
            )

        else:
            log_info(
                module=MODULE_NAME,
                action="column_check",
                message=f"Column '{column_name}' already exists with correct datatype '{required_type}'",
                status="SKIPPED",
            )

    # Drop extra columns
    required_column_names = set(required_columns.keys())
    existing_column_names = set(existing_columns.keys())

    extra_columns = existing_column_names - required_column_names

    for column_name in extra_columns:
        drop_extra_column(
            connection=connection,
            table_name=table_name,
            column_name=column_name,
        )

        log_warning(
            module=MODULE_NAME,
            action="drop_extra_column",
            message=f"Dropped extra column '{column_name}' from role_login table",
            status="SUCCESS",
        )

    log_info(
        module=MODULE_NAME,
        action="sync_role_login_schema",
        message="role_login table schema sync completed",
        status="SUCCESS",
    )


def initialize_role_login_table(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    """
    Checks role_login table and creates/syncs it.
    """

    table_name = "role_login"

    log_info(
        module=MODULE_NAME,
        action="initialize_role_login_table",
        message="Checking role_login table",
        status="STARTED",
    )

    if table_exists(connection, database_name, table_name):
        log_info(
            module=MODULE_NAME,
            action="table_check",
            message="Table 'role_login' already exists. Checking schema now.",
            status="SUCCESS",
        )

        sync_role_login_schema(
            connection=connection,
            database_name=database_name,
        )

    else:
        log_info(
            module=MODULE_NAME,
            action="table_check",
            message="Table 'role_login' does not exist. Creating now.",
            status="STARTED",
        )

        create_role_login_table(connection)

        log_info(
            module=MODULE_NAME,
            action="create_role_login_table",
            message="Table 'role_login' created successfully",
            status="SUCCESS",
        )


def initialize_database() -> None:
    """
    Main function to initialize CMP database and required base tables.
    """

    log_startup_banner()

    load_environment()

    config = get_mysql_config()
    database_name = config["database"]

    log_info(
        module=MODULE_NAME,
        action="initialize_database",
        message=f"Starting database initialization for '{database_name}'",
        status="STARTED",
    )

    try:
        validate_mysql_config(config)

        log_info(
            module=MODULE_NAME,
            action="mysql_connection_without_database",
            message=f"Connecting to MySQL server at {config['host']}:{config['port']}",
            status="STARTED",
        )

        server_connection = get_mysql_connection_without_database(config)

        try:
            log_info(
                module=MODULE_NAME,
                action="mysql_connection_without_database",
                message="Connected to MySQL server successfully",
                status="SUCCESS",
            )

            if database_exists(server_connection, database_name):
                log_info(
                    module=MODULE_NAME,
                    action="database_check",
                    message=f"Database '{database_name}' already exists. No action required.",
                    status="SKIPPED",
                )
            else:
                log_info(
                    module=MODULE_NAME,
                    action="database_check",
                    message=f"Database '{database_name}' does not exist. Creating now.",
                    status="STARTED",
                )

                create_database(server_connection, database_name)

                log_info(
                    module=MODULE_NAME,
                    action="create_database",
                    message=f"Database '{database_name}' created successfully",
                    status="SUCCESS",
                )

        finally:
            server_connection.close()

            log_info(
                module=MODULE_NAME,
                action="mysql_connection_without_database",
                message="MySQL server connection closed",
                status="SUCCESS",
            )

        log_info(
            module=MODULE_NAME,
            action="mysql_connection_with_database",
            message=f"Connecting to database '{database_name}'",
            status="STARTED",
        )

        db_connection = get_mysql_connection_with_database(config)

        try:
            log_info(
                module=MODULE_NAME,
                action="mysql_connection_with_database",
                message=f"Connected to database '{database_name}' successfully",
                status="SUCCESS",
            )

            initialize_role_login_table(
                connection=db_connection,
                database_name=database_name,
            )

        finally:
            db_connection.close()

            log_info(
                module=MODULE_NAME,
                action="mysql_connection_with_database",
                message="Database connection closed",
                status="SUCCESS",
            )

        log_info(
            module=MODULE_NAME,
            action="initialize_database",
            message=f"Database initialization completed for '{database_name}'",
            status="SUCCESS",
        )

    except Exception as exc:
        log_error(
            module=MODULE_NAME,
            action="initialize_database",
            message=f"Database initialization failed for '{database_name}'",
            error=exc,
            status="FAILED",
        )
        raise


if __name__ == "__main__":
    initialize_database()