"""PostgreSQL connection pool. Uses standard PG* environment variables (PGHOST, PGDATABASE, ...)."""
from contextlib import contextmanager
import os
import threading
from psycopg2.pool import ThreadedConnectionPool

_pool = None
_lock = threading.Lock()

def _get_pool():
    global _pool
    with _lock:
        if _pool is None:
            _pool = ThreadedConnectionPool(1, int(os.environ.get("DB_POOL_MAX", "30")))
        return _pool

@contextmanager
def connection():
    """Yields a connection; commits on success, rolls back on any exception."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
