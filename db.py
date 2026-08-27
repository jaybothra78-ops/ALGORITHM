"""Backward-compatible facade for db package."""
from db.connection import get_db_connection as connection, initialize_schema as initialize_database
from db.repository import SignalRepository

def save_signal(signal):
    return SignalRepository.save(signal)

def get_signals(scan_date, index=None, signal_type=None, strategy=None):
    return SignalRepository.get_signals(scan_date, index, signal_type, strategy)
