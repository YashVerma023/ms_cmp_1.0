"""
run.py

Main entry point of the CMP Operation Web App.

Flow:
1. Start project monitoring/logging
2. Create/check MySQL database `cmp`
3. Create/check/sync role_login table
4. Insert default users if missing
5. Import Flask app from app.py
6. Run the web application

Run command:
    python run.py
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent

if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


from helper import log_info, log_error, log_startup_banner
from database.creation import initialize_database
from database.default_user import seed_default_superadmin_user


MODULE_NAME = "run"


def start_database_setup() -> None:
    """
    Runs database creation/check process before starting the web app.
    """

    log_info(
        module=MODULE_NAME,
        action="start_database_setup",
        message="Starting database setup process",
        status="STARTED",
    )

    initialize_database()

    log_info(
        module=MODULE_NAME,
        action="start_database_setup",
        message="Database setup process completed successfully",
        status="SUCCESS",
    )


def start_default_user_setup() -> None:
    """
    Inserts default application users if missing.
    """

    log_info(
        module=MODULE_NAME,
        action="start_default_user_setup",
        message="Starting default user setup process",
        status="STARTED",
    )

    seed_default_superadmin_user()

    log_info(
        module=MODULE_NAME,
        action="start_default_user_setup",
        message="Default user setup process completed successfully",
        status="SUCCESS",
    )


def start_flask_app() -> None:
    """
    Imports and starts Flask web application.

    app.py should expose one Flask app object named `app`.
    """

    log_info(
        module=MODULE_NAME,
        action="start_flask_app",
        message="Importing Flask app from app.py",
        status="STARTED",
    )

    try:
        from app import app

        log_info(
            module=MODULE_NAME,
            action="start_flask_app",
            message="Flask app imported successfully",
            status="SUCCESS",
        )

        log_info(
            module=MODULE_NAME,
            action="run_flask_app",
            message="Starting Flask development server",
            status="STARTED",
        )

        app.run(
            host="0.0.0.0",
            port=5000,
            debug=True,
        )

    except ImportError as exc:
        log_error(
            module=MODULE_NAME,
            action="start_flask_app",
            message="Failed to import Flask app from app.py",
            error=exc,
            status="FAILED",
        )
        raise

    except Exception as exc:
        log_error(
            module=MODULE_NAME,
            action="run_flask_app",
            message="Flask application failed to start",
            error=exc,
            status="FAILED",
        )
        raise


def main() -> None:
    """
    Main execution flow.
    """

    try:
        log_startup_banner()

        log_info(
            module=MODULE_NAME,
            action="main",
            message="CMP Operation App startup initiated",
            status="STARTED",
        )

        start_database_setup()
        start_default_user_setup()
        start_flask_app()

    except Exception as exc:
        log_error(
            module=MODULE_NAME,
            action="main",
            message="CMP Operation App startup failed",
            error=exc,
            status="FAILED",
        )
        raise


if __name__ == "__main__":
    main()