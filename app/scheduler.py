"""Optional in-process schedulers (weekly digest + contract health)."""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

_scheduler_started = False
_scheduler = None


def _truthy(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


def init_schedulers(app) -> None:
    """Start APScheduler jobs when enabled via env."""
    global _scheduler_started, _scheduler
    if _scheduler_started:
        return

    want_digest = _truthy("ENABLE_WEEKLY_DIGEST_SCHEDULER")
    # Health monitor on by default so dashboards stay fresh in local/dev.
    want_health = _truthy("ENABLE_CONTRACT_HEALTH_SCHEDULER", "true")
    if not want_digest and not want_health:
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning(
            "APScheduler is not installed; schedulers disabled. "
            "Install APScheduler or set ENABLE_WEEKLY_DIGEST_SCHEDULER / ENABLE_CONTRACT_HEALTH_SCHEDULER."
        )
        return

    scheduler = BackgroundScheduler(daemon=True)

    if want_digest:

        def _digest_job():
            with app.app_context():
                from app.utils.weekly_digest import run_weekly_digests

                run_weekly_digests()

        scheduler.add_job(
            _digest_job,
            trigger="cron",
            day_of_week="mon",
            hour=9,
            minute=0,
            id="weekly_digest",
        )
        logger.info("Weekly digest scheduler started (Mondays 09:00).")

    if want_health:

        def _health_job():
            with app.app_context():
                from app.utils.contract_health import run_contract_health_scan

                result = run_contract_health_scan(with_ai=True)
                logger.info("Contract health scan: %s", result)

        # Every 4 hours
        scheduler.add_job(
            _health_job,
            trigger="interval",
            hours=4,
            id="contract_health",
            replace_existing=True,
        )
        logger.info("Contract health scheduler started (every 4 hours).")
        # Boot scan so dashboards aren't empty until the first interval tick.
        try:
            _health_job()
        except Exception:
            logger.exception("Contract health bootstrap scan failed")

    scheduler.start()
    _scheduler = scheduler
    _scheduler_started = True


def init_weekly_digest_scheduler(app) -> None:
    """Back-compat alias."""
    init_schedulers(app)


def start_scheduler_once(app) -> None:
    """Idempotent wrapper safe to call from create_app."""
    if _scheduler_started:
        return
    thread = threading.Thread(target=lambda: init_schedulers(app), daemon=True)
    thread.start()
