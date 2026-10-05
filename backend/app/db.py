import os
import psycopg
from psycopg.rows import dict_row


def connect():
    return psycopg.connect(
        os.environ.get('DATABASE_URL', ''), connect_timeout=3,
        row_factory=dict_row,
    )


def demo_enabled():
    return os.environ.get('DEMO_MODE', 'false').lower() == 'true'
