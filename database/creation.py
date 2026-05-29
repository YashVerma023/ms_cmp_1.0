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
7. Checking whether `server_info` table exists
8. Creating `server_info` table if it does not exist
9. Syncing `server_info` table schema:
   - Add missing columns
   - Modify columns with wrong datatype
   - Drop extra columns
10. Checking whether `clients` table exists
11. Creating `clients` table if it does not exist
12. Syncing `clients` table schema:
   - Add missing columns
   - Modify columns with wrong datatype
   - Drop extra columns
13. Logging all operations to terminal and logs/logs.csv

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


SERVER_INFO_SCHEMA = {
    "Server": "VARCHAR(10)",
    "Username": "VARCHAR(20)",
    "IP": "VARCHAR(20)",
    "Password": "VARCHAR(30)",
    "Stoxxo Id": "VARCHAR(30)",
    "Stoxxo Password": "VARCHAR(30)",
    "Algo": "VARCHAR(10)",
    "Expiry": "VARCHAR(20)",
    "Subscriptions": "INT",
    "Logins": "INT",
    "Active": "INT",
    "Avlbl": "INT",
    "Dte": "INT",
    "Aum": "VARCHAR(20)",
    "Remarks": "VARCHAR(30)",
    "Operator": "VARCHAR(20)",
}


CLIENTS_SCHEMA = {
    "userId": "VARCHAR(20)",
    "alias": "VARCHAR(50)",
    "Broker": "VARCHAR(20)",
    "server": "VARCHAR(10)",
    "algo": "VARCHAR(10)",
    "Running Type": "VARCHAR(20)",
    "Operator Name": "VARCHAR(20)",
    "Category": "VARCHAR(20)",
    "SubCategory": "VARCHAR(20)",
    "Acc Type": "VARCHAR(20)",
    "DealerID": "VARCHAR(30)",
}


GROUP_SCHEMA = {
    "group_name": "VARCHAR(30)",
    "group_def":  "VARCHAR(50)",
}

GROUP_CONFIG_SCHEMA = {
    "config_key": "VARCHAR(50)",
    "config_val": "TEXT",
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


def quote_mysql_identifier(identifier: str) -> str:
    """
    Safely quotes MySQL identifiers.

    Supports normal names:
        role_login -> `role_login`

    Also supports column names with spaces:
        Stoxxo Id -> `Stoxxo Id`
        Running Type -> `Running Type`
    """

    if identifier is None or str(identifier).strip() == "":
        raise ValueError("MySQL identifier cannot be empty")

    safe_identifier = str(identifier).replace("`", "``")
    return f"`{safe_identifier}`"


def validate_mysql_identifier(identifier: str) -> None:
    """
    Validates database and table names.

    Allows:
    - letters
    - numbers
    - underscore

    Note:
    This is intentionally strict for database/table names.
    Column names with spaces are handled using quote_mysql_identifier().
    """

    if not identifier:
        raise ValueError("MySQL identifier cannot be empty")

    if not identifier.replace("_", "").isalnum():
        raise ValueError(
            f"Invalid MySQL identifier '{identifier}'. Only letters, numbers, and underscores are allowed."
        )


def normalize_column_type(column_type: str) -> str:
    """
    Normalizes MySQL column datatype for comparison.

    Examples:
        varchar(20) -> VARCHAR(20)
        int -> INT
        int(11) -> INT
    """

    normalized_type = str(column_type).strip().upper()

    if normalized_type.startswith("INT"):
        return "INT"

    return normalized_type


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
        CREATE DATABASE {quote_mysql_identifier(database_name)}
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


def create_table_from_schema(
    connection: pymysql.connections.Connection,
    table_name: str,
    schema: dict[str, str],
) -> None:
    """
    Creates a table from a schema dictionary.

    Example schema:
        {
            "Server": "VARCHAR(10)",
            "Stoxxo Id": "VARCHAR(30)"
        }
    """

    validate_mysql_identifier(table_name)

    column_definitions = []

    for column_name, column_type in schema.items():
        column_definitions.append(
            f"{quote_mysql_identifier(column_name)} {column_type}"
        )

    columns_sql = ",\n            ".join(column_definitions)

    query = f"""
        CREATE TABLE {quote_mysql_identifier(table_name)} (
            {columns_sql}
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """

    with connection.cursor() as cursor:
        cursor.execute(query)


def create_role_login_table(connection: pymysql.connections.Connection) -> None:
    """
    Creates role_login table with the required schema.
    """

    create_table_from_schema(
        connection=connection,
        table_name="role_login",
        schema=ROLE_LOGIN_SCHEMA,
    )


def create_server_info_table(connection: pymysql.connections.Connection) -> None:
    """
    Creates server_info table with the required schema.
    """

    create_table_from_schema(
        connection=connection,
        table_name="server_info",
        schema=SERVER_INFO_SCHEMA,
    )


def create_clients_table(connection: pymysql.connections.Connection) -> None:
    """
    Creates clients table with the required schema.
    """

    create_table_from_schema(
        connection=connection,
        table_name="clients",
        schema=CLIENTS_SCHEMA,
    )


def get_existing_columns(
    connection: pymysql.connections.Connection,
    database_name: str,
    table_name: str,
) -> dict:
    """
    Returns current table columns with their full datatype.

    Example output:
        {
            "role": "VARCHAR(20)",
            "name": "VARCHAR(30)",
            "Subscriptions": "INT"
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
        row["COLUMN_NAME"]: normalize_column_type(row["COLUMN_TYPE"])
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

    query = f"""
        ALTER TABLE {quote_mysql_identifier(table_name)}
        ADD COLUMN {quote_mysql_identifier(column_name)} {column_type}
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

    query = f"""
        ALTER TABLE {quote_mysql_identifier(table_name)}
        MODIFY COLUMN {quote_mysql_identifier(column_name)} {column_type}
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

    query = f"""
        ALTER TABLE {quote_mysql_identifier(table_name)}
        DROP COLUMN {quote_mysql_identifier(column_name)}
    """

    with connection.cursor() as cursor:
        cursor.execute(query)


def sync_table_schema(
    connection: pymysql.connections.Connection,
    database_name: str,
    table_name: str,
    required_columns: dict[str, str],
) -> None:
    """
    Synchronizes a table with required schema.

    Actions:
    1. Add missing columns
    2. Modify columns with wrong datatype
    3. Drop extra columns
    """

    validate_mysql_identifier(table_name)

    log_info(
        module=MODULE_NAME,
        action=f"sync_{table_name}_schema",
        message=f"Starting {table_name} table schema sync",
        status="STARTED",
    )

    existing_columns = get_existing_columns(
        connection=connection,
        database_name=database_name,
        table_name=table_name,
    )

    # Add missing columns and modify wrong datatypes
    for column_name, required_type in required_columns.items():
        existing_type = existing_columns.get(column_name)
        normalized_required_type = normalize_column_type(required_type)

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
                message=(
                    f"Added missing column '{column_name}' "
                    f"with datatype '{required_type}' in table '{table_name}'"
                ),
                status="SUCCESS",
            )

        elif existing_type != normalized_required_type:
            modify_existing_column(
                connection=connection,
                table_name=table_name,
                column_name=column_name,
                column_type=required_type,
            )

            log_info(
                module=MODULE_NAME,
                action="modify_existing_column",
                message=(
                    f"Modified column '{column_name}' in table '{table_name}' "
                    f"from '{existing_type}' to '{required_type}'"
                ),
                status="SUCCESS",
            )

        else:
            log_info(
                module=MODULE_NAME,
                action="column_check",
                message=(
                    f"Column '{column_name}' already exists with correct "
                    f"datatype '{required_type}' in table '{table_name}'"
                ),
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
            message=f"Dropped extra column '{column_name}' from table '{table_name}'",
            status="SUCCESS",
        )

    log_info(
        module=MODULE_NAME,
        action=f"sync_{table_name}_schema",
        message=f"{table_name} table schema sync completed",
        status="SUCCESS",
    )


def sync_role_login_schema(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    """
    Synchronizes role_login table with required schema.
    """

    sync_table_schema(
        connection=connection,
        database_name=database_name,
        table_name="role_login",
        required_columns=ROLE_LOGIN_SCHEMA,
    )


def sync_server_info_schema(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    """
    Synchronizes server_info table with required schema.
    """

    sync_table_schema(
        connection=connection,
        database_name=database_name,
        table_name="server_info",
        required_columns=SERVER_INFO_SCHEMA,
    )


def sync_clients_schema(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    """
    Synchronizes clients table with required schema.
    """

    sync_table_schema(
        connection=connection,
        database_name=database_name,
        table_name="clients",
        required_columns=CLIENTS_SCHEMA,
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


def initialize_server_info_table(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    """
    Checks server_info table and creates/syncs it.
    """

    table_name = "server_info"

    log_info(
        module=MODULE_NAME,
        action="initialize_server_info_table",
        message="Checking server_info table",
        status="STARTED",
    )

    if table_exists(connection, database_name, table_name):
        log_info(
            module=MODULE_NAME,
            action="table_check",
            message="Table 'server_info' already exists. Checking schema now.",
            status="SUCCESS",
        )

        sync_server_info_schema(
            connection=connection,
            database_name=database_name,
        )

    else:
        log_info(
            module=MODULE_NAME,
            action="table_check",
            message="Table 'server_info' does not exist. Creating now.",
            status="STARTED",
        )

        create_server_info_table(connection)

        log_info(
            module=MODULE_NAME,
            action="create_server_info_table",
            message="Table 'server_info' created successfully",
            status="SUCCESS",
        )


def initialize_clients_table(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    """
    Checks clients table and creates/syncs it.
    """

    table_name = "clients"

    log_info(
        module=MODULE_NAME,
        action="initialize_clients_table",
        message="Checking clients table",
        status="STARTED",
    )

    if table_exists(connection, database_name, table_name):
        log_info(
            module=MODULE_NAME,
            action="table_check",
            message="Table 'clients' already exists. Checking schema now.",
            status="SUCCESS",
        )

        sync_clients_schema(
            connection=connection,
            database_name=database_name,
        )

    else:
        log_info(
            module=MODULE_NAME,
            action="table_check",
            message="Table 'clients' does not exist. Creating now.",
            status="STARTED",
        )

        create_clients_table(connection)

        log_info(
            module=MODULE_NAME,
            action="create_clients_table",
            message="Table 'clients' created successfully",
            status="SUCCESS",
        )


def sync_group_schema(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    sync_table_schema(
        connection=connection,
        database_name=database_name,
        table_name="group",
        required_columns=GROUP_SCHEMA,
    )


def initialize_group_table(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    """
    Checks group table and creates/syncs it.
    """

    table_name = "group"

    log_info(
        module=MODULE_NAME,
        action="initialize_group_table",
        message="Checking group table",
        status="STARTED",
    )

    if table_exists(connection, database_name, table_name):
        log_info(
            module=MODULE_NAME,
            action="table_check",
            message="Table 'group' already exists. Checking schema now.",
            status="SUCCESS",
        )
        sync_group_schema(connection=connection, database_name=database_name)
    else:
        log_info(
            module=MODULE_NAME,
            action="table_check",
            message="Table 'group' does not exist. Creating now.",
            status="STARTED",
        )
        create_table_from_schema(
            connection=connection,
            table_name="group",
            schema=GROUP_SCHEMA,
        )
        log_info(
            module=MODULE_NAME,
            action="create_group_table",
            message="Table 'group' created successfully",
            status="SUCCESS",
        )


def sync_group_config_schema(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    sync_table_schema(
        connection=connection,
        database_name=database_name,
        table_name="group_config",
        required_columns=GROUP_CONFIG_SCHEMA,
    )


def initialize_group_config_table(
    connection: pymysql.connections.Connection,
    database_name: str,
) -> None:
    """Creates or syncs the group_config key-value config table."""
    table_name = "group_config"
    log_info(module=MODULE_NAME, action="initialize_group_config_table",
             message="Checking group_config table", status="STARTED")

    if table_exists(connection, database_name, table_name):
        sync_group_config_schema(connection=connection, database_name=database_name)
    else:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE group_config (
                    config_key VARCHAR(50) NOT NULL,
                    config_val TEXT,
                    PRIMARY KEY (config_key)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        log_info(module=MODULE_NAME, action="create_group_config_table",
                 message="Table 'group_config' created successfully", status="SUCCESS")


def initialize_database() -> None:
    """
    Main function to initialize CMP database and required base tables.
    """

    log_startup_banner()

    load_environment()
    config = get_mysql_config()
    validate_mysql_config(config)

    database_name = config["database"]

    log_info(
        module=MODULE_NAME,
        action="initialize_database",
        message="Starting database initialization",
        status="STARTED",
    )

    try:
        log_info(
            module=MODULE_NAME,
            action="mysql_connection_without_database",
            message="Connecting to MySQL server",
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

            initialize_clients_table(
                connection=db_connection,
                database_name=database_name,
            )

            initialize_group_table(
                connection=db_connection,
                database_name=database_name,
            )

            initialize_group_config_table(
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

    except Exception as exc:
        log_error(
            module=MODULE_NAME,
            action="initialize_database",
            message="Database initialization failed",
            error=exc,
            status="FAILED",
        )
        raise


if __name__ == "__main__":
    initialize_database()
