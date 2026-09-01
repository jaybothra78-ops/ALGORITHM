"""Pytest configuration and database isolation fixtures."""
import os
import shutil
import pytest
from core.config import settings


@pytest.fixture(scope="session", autouse=True)
def isolate_test_database(tmp_path_factory):
    """Ensure all automated tests run against an isolated temporary database."""
    test_dir = tmp_path_factory.mktemp("test_db")
    test_db = test_dir / "test_scanner.db"
    
    # Override settings DATABASE_PATH during test session
    original_db_path = settings.DATABASE_PATH
    settings.DATABASE_PATH = test_db

    from db.connection import initialize_schema
    from db.paper_repository import PaperRepository

    initialize_schema()
    PaperRepository.initialize_paper_tables()

    yield

    # Restore original path
    settings.DATABASE_PATH = original_db_path
