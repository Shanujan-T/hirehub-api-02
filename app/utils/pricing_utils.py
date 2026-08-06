from __future__ import annotations

from decimal import Decimal
from statistics import mean

from sqlalchemy import func

from app.extensions import db
from app.models.category_model import Category
from app.models.category_pricing_model import CategoryPricing
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.utils import utc_now
from app.utils.scope_utils import parse_json_value

# Minimum samples before a data-backed tier is used.
MIN_SAMPLES = 3


def recalc_category_pricing(category_id, location):
    """Recalculate average price for a category + location from completed contracts."""
    result = (
        db.session.query(
            func.avg(Contract.total_amount),
            func.count(Contract.id),
        )
        .join(Contract.job)
        .filter(
            Contract.status == "completed",
            Contract.job.has(category_id=category_id, location=location),
        )
        .first()
    )

    avg_price = result[0] if result and result[0] else Decimal("0")
    sample_size = result[1] if result else 0

    pricing = CategoryPricing.query.filter_by(
        category_id=category_id, location=location
    ).first()

    if pricing:
        pricing.average_price = avg_price or Decimal("0")
        pricing.sample_size = sample_size
        pricing.last_updated = utc_now()
    else:
        pricing = CategoryPricing(
            category_id=category_id,
            location=location,
            average_price=avg_price or Decimal("0"),
            sample_size=sample_size,
            last_updated=utc_now(),
        )
        db.session.add(pricing)

    db.session.commit()
    return pricing


def _baseline_estimate(category: Category | None, scope_data: dict) -> float | None:
    if not category or category.baseline_price is None:
        return None
    baseline = float(category.baseline_price)
    if category.baseline_unit == "per_sqft":
        area = scope_data.get("area_sqft")
        try:
            area_val = float(area)
        except (TypeError, ValueError):
            area_val = None
        if area_val is not None and area_val > 0:
            return round(baseline * area_val, 2)
        return round(baseline, 2)
    return round(baseline, 2)


def _completed_jobs_with_amounts(category_id: int, location: str) -> list[tuple[Job, float]]:
    """Tier 1 source: completed contracts for category + location."""
    rows = (
        db.session.query(Job, Contract.total_amount)
        .join(Contract, Contract.job_id == Job.id)
        .filter(
            Contract.status == "completed",
            Job.category_id == category_id,
            Job.location == location,
            Contract.total_amount.isnot(None),
        )
        .all()
    )
    out: list[tuple[Job, float]] = []
    for job, amount in rows:
        try:
            out.append((job, float(amount)))
        except (TypeError, ValueError):
            continue
    return out


def _posted_jobs_with_prices(
    category_id: int, location: str, exclude_job_id: int | None = None
) -> list[tuple[Job, float]]:
    """Tier 2 source: all posted jobs' asking prices (final_price), any status."""
    q = Job.query.filter(
        Job.category_id == category_id,
        Job.location == location,
        Job.final_price.isnot(None),
    )
    if exclude_job_id is not None:
        q = q.filter(Job.id != exclude_job_id)
    out: list[tuple[Job, float]] = []
    for job in q.all():
        try:
            price = float(job.final_price)
        except (TypeError, ValueError):
            continue
        if price < 0:
            continue
        out.append((job, price))
    return out


def _numeric_price_per_unit(
    history: list[tuple[Job, float]], field_key: str, current_value: float
) -> tuple[float | None, int]:
    ppus: list[float] = []
    for job, amount in history:
        data = job.get_scope_data() or {}
        raw = data.get(field_key)
        try:
            units = float(raw)
        except (TypeError, ValueError):
            continue
        if units <= 0:
            continue
        ppus.append(amount / units)
    if len(ppus) < MIN_SAMPLES or current_value <= 0:
        return None, len(ppus)
    return round(mean(ppus) * current_value, 2), len(ppus)


def _multiselect_delta(
    history: list[tuple[Job, float]], field_key: str, selected: list[str]
) -> tuple[float, int]:
    """Sum with-vs-without average deltas for selected features with enough data."""
    total_delta = 0.0
    adjusted_features = 0
    for feature in selected:
        with_prices: list[float] = []
        without_prices: list[float] = []
        for job, amount in history:
            data = job.get_scope_data() or {}
            features = data.get(field_key) or []
            if isinstance(features, str):
                features = [features]
            if not isinstance(features, list):
                continue
            if feature in features:
                with_prices.append(amount)
            else:
                without_prices.append(amount)
        if len(with_prices) >= MIN_SAMPLES and len(without_prices) >= MIN_SAMPLES:
            total_delta += mean(with_prices) - mean(without_prices)
            adjusted_features += 1
    return total_delta, adjusted_features


def _result(price, sample_size, method, note):
    return {
        "suggested_price": price,
        "average_price": price,
        "sample_size": sample_size,
        "method": method,
        "note": note,
    }


def _apply_scope_to_history(
    history: list[tuple[Job, float]],
    schema: list,
    scope_data: dict,
    *,
    flat_method: str,
    allow_multiselect: bool,
) -> dict | None:
    """
    Build a suggestion from job+amount pairs.

    Returns None if there are fewer than MIN_SAMPLES rows.
    Scope-adjusted numeric (and optionally multiselect) refinements apply when possible;
    otherwise the flat mean is used.
    """
    if len(history) < MIN_SAMPLES:
        return None

    sample_size = len(history)
    suggested = round(mean(amount for _, amount in history), 2)
    used_scope = False

    if flat_method == "historical_average":
        note = (
            f"Based on {sample_size} completed job"
            f"{'s' if sample_size != 1 else ''} in this area."
        )
    else:
        note = (
            f"Based on {sample_size} similar job posting"
            f"{'s' if sample_size != 1 else ''} (asking prices, not yet completed)."
        )

    if schema and scope_data:
        for field in schema:
            if field.get("type") != "number":
                continue
            key = field.get("key")
            if not key or key not in scope_data:
                continue
            try:
                current = float(scope_data[key])
            except (TypeError, ValueError):
                continue
            estimate, n = _numeric_price_per_unit(history, key, current)
            if estimate is not None:
                suggested = estimate
                sample_size = max(sample_size, n)
                used_scope = True
                if flat_method == "historical_average":
                    note = (
                        f"Based on {sample_size} completed jobs in this area "
                        "(size-adjusted)."
                    )
                else:
                    note = (
                        f"Based on {sample_size} similar job postings "
                        "(asking prices, size-adjusted)."
                    )
                break

        if allow_multiselect:
            for field in schema:
                if field.get("type") != "multiselect":
                    continue
                key = field.get("key")
                if not key or key not in scope_data:
                    continue
                selected = scope_data[key]
                if isinstance(selected, str):
                    selected = [selected]
                if not isinstance(selected, list) or not selected:
                    continue
                delta, adjusted = _multiselect_delta(
                    history, key, [str(s) for s in selected]
                )
                if adjusted:
                    suggested = round(float(suggested) + delta, 2)
                    used_scope = True
                    note = (
                        f"Based on {sample_size} completed jobs in this area "
                        "(feature-adjusted)."
                    )

    # Tier 1 keeps scope_adjusted when refined; Tier 2 always reports posted_jobs_average.
    if used_scope and flat_method == "historical_average":
        method = "scope_adjusted"
    else:
        method = flat_method

    return _result(suggested, sample_size, method, note)


def get_pricing_suggestion(
    category_id,
    location,
    scope_data=None,
    scope_schema=None,
    exclude_job_id=None,
):
    """
    Suggest a price for category + location.

    Tier order:
      1. Completed contracts (3+) → historical_average / scope_adjusted
      2. Posted jobs' final_price (3+) → posted_jobs_average
      3. category.baseline_price → baseline_estimate
      4. nothing → insufficient_data
    """
    category = Category.query.get(category_id)

    if isinstance(scope_data, str):
        scope_data = parse_json_value(scope_data)
    if not isinstance(scope_data, dict):
        scope_data = {}

    schema = scope_schema
    if isinstance(schema, str):
        schema = parse_json_value(schema)
    if schema is None and category is not None:
        schema = category.get_scope_schema()
    if not isinstance(schema, list):
        schema = []

    # --- Tier 1: completed contracts ---
    completed = _completed_jobs_with_amounts(category_id, location)
    tier1 = _apply_scope_to_history(
        completed,
        schema,
        scope_data,
        flat_method="historical_average",
        allow_multiselect=True,
    )
    if tier1 is not None:
        return tier1

    # --- Tier 2: posted jobs asking prices ---
    posted = _posted_jobs_with_prices(category_id, location, exclude_job_id=exclude_job_id)
    tier2 = _apply_scope_to_history(
        posted,
        schema,
        scope_data,
        flat_method="posted_jobs_average",
        allow_multiselect=False,
    )
    if tier2 is not None:
        return tier2

    # --- Tier 3: admin baseline ---
    baseline = _baseline_estimate(category, scope_data)
    if baseline is not None:
        unit = category.baseline_unit if category else None
        note = (
            "Estimated from category baseline (per sq ft) — no local data yet."
            if unit == "per_sqft"
            else "Estimated from category baseline — no local data yet."
        )
        return _result(baseline, 0, "baseline_estimate", note)

    # --- Tier 4 ---
    return _result(
        None,
        0,
        "insufficient_data",
        "No pricing data for this category + location yet.",
    )
