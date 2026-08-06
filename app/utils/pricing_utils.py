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
from app.utils.scope_utils import (
    format_unit_phrase,
    parse_json_value,
    pricing_fields,
)
from app.utils.sri_lanka_districts import (
    DISTRICT_TIERS,
    district_multiplier,
    match_district,
)

# Minimum samples before a data-backed tier is used.
MIN_SAMPLES = 3


def recalc_category_pricing(category_id, location):
    """Recalculate average price for a category + location from completed contracts.

    When real samples exist, clears is_seeded_estimate so seeded rows never win again.
    """
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
        if sample_size > 0:
            pricing.is_seeded_estimate = False
    else:
        pricing = CategoryPricing(
            category_id=category_id,
            location=location,
            average_price=avg_price or Decimal("0"),
            sample_size=sample_size,
            is_seeded_estimate=False if sample_size > 0 else True,
            last_updated=utc_now(),
        )
        db.session.add(pricing)

    db.session.commit()
    return pricing


def seed_district_pricing(category_id: int | None = None) -> dict:
    """
    Seed/update CategoryPricing for all 25 districts from category.baseline_price.

    - Uses Colombo baseline × district cost-of-living multiplier
      (Numbeo-backed cache when available, else legacy tier constants).
    - Never overwrites rows with sample_size > 0 (real contract data).
    - Only refreshes rows still flagged is_seeded_estimate (or missing rows).
    """
    if category_id is not None:
        categories = Category.query.filter_by(id=int(category_id)).all()
    else:
        categories = Category.query.filter_by(status="approved").all()

    created = updated = skipped = 0
    for cat in categories:
        if cat.baseline_price is None:
            skipped += 1
            continue
        base = float(cat.baseline_price)
        for district in DISTRICT_TIERS:
            price = round(base * district_multiplier(district), 2)
            row = CategoryPricing.query.filter_by(
                category_id=cat.id, location=district
            ).first()
            if row:
                # Never overwrite real accumulated contract data
                if row.sample_size and int(row.sample_size) > 0:
                    skipped += 1
                    continue
                row.average_price = price
                row.sample_size = 0
                row.is_seeded_estimate = True
                row.last_updated = utc_now()
                updated += 1
            else:
                db.session.add(
                    CategoryPricing(
                        category_id=cat.id,
                        location=district,
                        average_price=price,
                        sample_size=0,
                        is_seeded_estimate=True,
                        last_updated=utc_now(),
                    )
                )
                created += 1

    db.session.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def _float_or_none(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
    return n


# ---------------------------------------------------------------------------
# Generic scope-based scaling (driven by category.scope_schema / scope_fields).
# Never hardcode field names like word_count / area_sqft here.
#
# For each numeric field with affects_price=true:
#   ratio = submitted_value / unit_size
# If MULTIPLE such fields have values, ratios are MULTIPLIED together
# (independent scope dimensions, e.g. area × rooms). Fields without a
# submitted value are skipped so the UI can show the per-unit reference rate
# before the poster fills everything in.
# ---------------------------------------------------------------------------


def _schema_for(category: Category | None, scope_schema=None) -> list:
    if isinstance(scope_schema, list):
        return scope_schema
    if category is not None:
        schema = category.get_scope_schema()
        if isinstance(schema, list):
            return schema
    return []


def _scope_scale_factor(schema: list, scope_data: dict) -> tuple[float, list[dict]]:
    """Return (scale_factor, used_fields) from affects_price number fields."""
    fields = pricing_fields(schema)
    if not fields:
        return 1.0, []

    factor = 1.0
    used: list[dict] = []
    for field in fields:
        key = field.get("key")
        if not key:
            continue
        value = _float_or_none(scope_data.get(key))
        if value is None or value <= 0:
            continue
        try:
            unit_size = float(field.get("unit_size") or 1)
        except (TypeError, ValueError):
            unit_size = 1.0
        if unit_size <= 0:
            unit_size = 1.0
        factor *= value / unit_size
        used.append(field)

    if not used:
        return 1.0, []
    return factor, used


def _unit_scope_provided(category: Category | None, scope_data: dict, schema=None) -> bool:
    """True when at least one affects_price numeric scope value was supplied."""
    schema = _schema_for(category, schema)
    _, used = _scope_scale_factor(schema, scope_data or {})
    return bool(used)


def _baseline_estimate(category: Category | None, scope_data: dict, schema=None) -> float | None:
    """Scale category.baseline_price by generic scope field ratios when present."""
    if not category or category.baseline_price is None:
        return None
    baseline = float(category.baseline_price)
    schema = _schema_for(category, schema)
    factor, _used = _scope_scale_factor(schema, scope_data or {})
    return round(baseline * factor, 2)


def _scale_reference_price(
    reference: float, category: Category | None, scope_data: dict, schema=None
) -> float:
    """Apply generic scope scaling to a district/base reference price."""
    schema = _schema_for(category, schema)
    factor, _used = _scope_scale_factor(schema, scope_data or {})
    return round(float(reference) * factor, 2)


def _baseline_note(category: Category | None, scope_data: dict | None = None, schema=None) -> str:
    schema = _schema_for(category, schema)
    fields = pricing_fields(schema)
    if not fields:
        return "Estimated (no local data yet)"
    _, used = _scope_scale_factor(schema, scope_data or {})
    phrases = [format_unit_phrase(f) for f in (used or fields)]
    seen: set[str] = set()
    unique: list[str] = []
    for phrase in phrases:
        if phrase not in seen:
            seen.add(phrase)
            unique.append(phrase)
    return f"Estimated from category baseline ({', '.join(unique)})"


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


def _result(price, sample_size, method, note, *, is_seeded_estimate: bool = False):
    return {
        "suggested_price": price,
        "average_price": price,
        "sample_size": sample_size,
        "method": method,
        "note": note,
        "is_seeded_estimate": bool(is_seeded_estimate),
    }


def _scale_reference_price(
    reference: float, category: Category | None, scope_data: dict, schema=None
) -> float:
    """Apply generic scope scaling to a district/base reference price."""
    schema = _schema_for(category, schema)
    factor, _used = _scope_scale_factor(schema, scope_data or {})
    return round(float(reference) * factor, 2)


def _lookup_district_pricing(category_id: int, location: str | None):
    """Return (CategoryPricing|None, canonical_district|None)."""
    district = match_district(location)
    if not district:
        return None, None
    row = CategoryPricing.query.filter_by(
        category_id=category_id, location=district
    ).first()
    return row, district


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
        # Prefer affects_price number fields; fall back to any number field for
        # historical price-per-unit adjustment (legacy schemas without the flag).
        preferred = pricing_fields(schema)
        number_fields = preferred or [
            f for f in schema if isinstance(f, dict) and f.get("type") == "number"
        ]
        for field in number_fields:
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
                unit_bit = f" ({format_unit_phrase(field)})"
                if flat_method == "historical_average":
                    note = (
                        f"Based on {sample_size} completed jobs in this area "
                        f"(size-adjusted{unit_bit})."
                    )
                else:
                    note = (
                        f"Based on {sample_size} similar job postings "
                        f"(asking prices, size-adjusted{unit_bit})."
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

    Order:
      1. CategoryPricing with real samples (sample_size > 0) for matched district
      2. Completed contracts (3+) → historical_average / scope_adjusted
      3. Posted jobs' final_price (3+) → posted_jobs_average
      4. Seeded CategoryPricing estimate for district (is_seeded_estimate)
      5. category.baseline_price (Tier-1 Colombo reference)
      6. insufficient_data
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

    pricing_row, district = _lookup_district_pricing(category_id, location)

    # --- District table: real accumulated data ---
    if pricing_row and pricing_row.sample_size and pricing_row.sample_size > 0:
        scaled = _scale_reference_price(
            float(pricing_row.average_price), category, scope_data, schema
        )
        note = (
            f"Estimated from local completed contracts"
            + (f" in {district}" if district else "")
        )
        _, used = _scope_scale_factor(schema, scope_data)
        if used:
            note = f"{note} ({', '.join(format_unit_phrase(f) for f in used)})"
        return _result(
            scaled,
            int(pricing_row.sample_size),
            "historical_average",
            note + ".",
            is_seeded_estimate=False,
        )

    # --- Live completed contracts ---
    completed = _completed_jobs_with_amounts(category_id, location)
    tier1 = _apply_scope_to_history(
        completed,
        schema,
        scope_data,
        flat_method="historical_average",
        allow_multiselect=True,
    )
    if tier1 is not None:
        if (
            tier1.get("method") != "scope_adjusted"
            and _unit_scope_provided(category, scope_data, schema)
        ):
            baseline = _baseline_estimate(category, scope_data, schema)
            if baseline is not None:
                return _result(
                    baseline,
                    0,
                    "baseline_estimate",
                    _baseline_note(category, scope_data, schema),
                    is_seeded_estimate=True,
                )
        tier1["is_seeded_estimate"] = False
        if not tier1.get("note"):
            tier1["note"] = "Estimated from local completed contracts"
        return tier1

    # --- Live posted jobs ---
    posted = _posted_jobs_with_prices(category_id, location, exclude_job_id=exclude_job_id)
    tier2 = _apply_scope_to_history(
        posted,
        schema,
        scope_data,
        flat_method="posted_jobs_average",
        allow_multiselect=False,
    )
    if tier2 is not None:
        if (
            tier2.get("method") != "scope_adjusted"
            and _unit_scope_provided(category, scope_data, schema)
        ):
            baseline = _baseline_estimate(category, scope_data, schema)
            if baseline is not None:
                return _result(
                    baseline,
                    0,
                    "baseline_estimate",
                    _baseline_note(category, scope_data, schema),
                    is_seeded_estimate=True,
                )
        tier2["is_seeded_estimate"] = False
        return tier2

    # --- Seeded district estimate (sample_size == 0 rows are estimates) ---
    if pricing_row and (
        pricing_row.is_seeded_estimate or not (pricing_row.sample_size or 0)
    ):
        scaled = _scale_reference_price(
            float(pricing_row.average_price), category, scope_data, schema
        )
        note = "Estimated (regional baseline — no completed contracts yet)"
        _, used = _scope_scale_factor(schema, scope_data)
        if used:
            note = (
                f"Estimated (regional baseline — no completed contracts yet; "
                f"{', '.join(format_unit_phrase(f) for f in used)})"
            )
        return _result(
            scaled,
            0,
            "seeded_district_estimate",
            note,
            is_seeded_estimate=True,
        )

    # --- Tier-1 Colombo / category base ---
    baseline = _baseline_estimate(category, scope_data, schema)
    if baseline is not None:
        note = _baseline_note(category, scope_data, schema)
        if not pricing_fields(schema):
            note = "Estimated (no local data yet)"
        return _result(
            baseline,
            0,
            "baseline_estimate",
            note,
            is_seeded_estimate=True,
        )

    return _result(
        None,
        0,
        "insufficient_data",
        "No pricing data for this category + location yet.",
        is_seeded_estimate=False,
    )
