"""
Background job queue (Phase 2).

RQ (Redis) when REDIS_URL is set; otherwise runs inline (dev/test). `enqueue` is
the single seam — production schedules a worker job; tests patch it to record
calls and drive the run state machine deterministically.
"""
import os
import logging

logger = logging.getLogger("jobs")


def enqueue(func, *args):
    """Schedule `func(*args)` on the worker queue (or run inline if no Redis)."""
    url = os.getenv("REDIS_URL")
    if url:
        from rq import Queue
        from redis import Redis
        return Queue("tax-agent", connection=Redis.from_url(url)).enqueue(func, *args)
    logger.debug("REDIS_URL unset — running %s inline", getattr(func, "__name__", func))
    return func(*args)
