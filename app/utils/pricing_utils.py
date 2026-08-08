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
# ---------------------------------------------------------------------------


def scale_price(base_rate: float, scope_data: dict, scope_key: str | None) -> float:
    if scope_key and scope_data:
        try:
            val = float(scope_data.get(scope_key))
            if val > 0:
                return base_rate * val
        except (TypeError, ValueError):
            pass
    return base_rate


def _schema_for(category: Category | None, scope_schema=None) -> list:
    if isinstance(scope_schema, list):
        return scope_schema
    if category is not None:
        schema = category.get_scope_schema()
        if isinstance(schema, list):
            return schema
    return []


def _unit_scope_provided(category: Category | None, scope_data: dict, schema=None) -> bool:
    """True when baseline_scope_key numeric scope value was supplied."""
    if not category or not category.baseline_scope_key:
        return False
    val = _float_or_none(scope_data.get(category.baseline_scope_key))
    return val is not None and val > 0


def _baseline_estimate(category: Category | None, scope_data: dict, schema=None) -> float | None:
    """Scale category.baseline_price by baseline_scope_key key when present."""
    if not category or category.baseline_price is None:
        return None
    baseline = float(category.baseline_price)
    return round(scale_price(baseline, scope_data, category.baseline_scope_key), 2)


def _scale_reference_price(
    reference: float, category: Category | None, scope_data: dict, schema=None
) -> float:
    """Apply baseline_scope_key scaling to a district/base reference price."""
    scope_key = category.baseline_scope_key if category else None
    return round(scale_price(float(reference), scope_data, scope_key), 2)


def _baseline_note(category: Category | None, scope_data: dict | None = None, schema=None) -> str:
    if not category or not category.baseline_scope_key:
        return "Estimated (no local data yet)"
    schema = _schema_for(category, schema)
    field = next((f for f in schema if isinstance(f, dict) and f.get("key") == category.baseline_scope_key), None)
    if field:
        return f"Estimated from category baseline ({format_unit_phrase(field)})"
    return "Estimated (no local data yet)"


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
    scope_key: str | None,
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
        if scope_key and scope_data:
            field = next((f for f in schema if isinstance(f, dict) and f.get("key") == scope_key), None)
            if field and field.get("type") == "number":
                ppus: list[float] = []
                for job, amount in history:
                    job_val = _float_or_none((job.get_scope_data() or {}).get(scope_key))
                    if job_val and job_val > 0:
                        ppus.append(amount / job_val)
                if len(ppus) >= MIN_SAMPLES:
                    current_val = _float_or_none(scope_data.get(scope_key))
                    if current_val and current_val > 0:
                        avg_ppu = mean(ppus)
                        suggested = round(scale_price(avg_ppu, scope_data, scope_key), 2)
                        sample_size = len(ppus)
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

    scope_key = category.baseline_scope_key if category else None
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
        if category and category.baseline_scope_key:
            val = _float_or_none(scope_data.get(category.baseline_scope_key))
            if val is not None and val > 0:
                field = next((f for f in schema if isinstance(f, dict) and f.get("key") == category.baseline_scope_key), None)
                if field:
                    note = f"{note} ({format_unit_phrase(field)})"
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
        scope_key,
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
        scope_key,
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
        if category and category.baseline_scope_key:
            val = _float_or_none(scope_data.get(category.baseline_scope_key))
            if val is not None and val > 0:
                field = next((f for f in schema if isinstance(f, dict) and f.get("key") == category.baseline_scope_key), None)
                if field:
                    note = (
                        f"Estimated (regional baseline — no completed contracts yet; "
                        f"{format_unit_phrase(field)})"
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
        if not category or not category.baseline_scope_key:
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


def suggest_price(category: str, quantity: float | int, district: str, scope: str | None = None) -> int | None:
    from app.models.pricing_reference_model import PricingReference
    from sqlalchemy import func

    # 1. Fetch all PricingReference rows for category, sorted by quantity
    rows = (
        PricingReference.query.filter(func.lower(PricingReference.category) == func.lower(category))
        .order_by(PricingReference.quantity.asc())
        .all()
    )
    if not rows:
        return None

    requested_qty = quantity
    try:
        requested_qty = float(quantity)
        if requested_qty.is_integer():
            requested_qty = int(requested_qty)
    except (TypeError, ValueError):
        requested_qty = 1

    # 2. Check if a row's quantity exactly matches requested quantity
    exact_match = next((r for r in rows if r.quantity == requested_qty), None)
    
    is_quantity_scaled = len([r for r in rows if r.quantity > 1]) > 1

    base_price = None

    if is_quantity_scaled:
        if exact_match:
            base_price = float(exact_match.base_price)
        elif requested_qty > rows[-1].quantity:
            # Extrapolate using highest tier's rate
            highest_tier = rows[-1]
            rate = float(highest_tier.base_price) / highest_tier.quantity
            base_price = rate * requested_qty
        elif requested_qty < rows[0].quantity:
            # Below lowest tier: extrapolate using lowest tier's rate
            lowest_tier = rows[0]
            rate = float(lowest_tier.base_price) / lowest_tier.quantity
            base_price = rate * requested_qty
        else:
            # Interpolate
            lower_tier = max((r for r in rows if r.quantity < requested_qty), key=lambda r: r.quantity)
            upper_tier = min((r for r in rows if r.quantity > requested_qty), key=lambda r: r.quantity)
            rate_lower = float(lower_tier.base_price) / lower_tier.quantity
            rate_upper = float(upper_tier.base_price) / upper_tier.quantity
            
            # Linear interpolation of per-unit rate
            t = (requested_qty - lower_tier.quantity) / (upper_tier.quantity - lower_tier.quantity)
            rate = rate_lower + t * (rate_upper - rate_lower)
            base_price = rate * requested_qty
    else:
        # Flat one-off category
        matched_row = None
        cleaned_req_scope = str(scope or "").strip().lower()
        if cleaned_req_scope:
            # 1. Try exact match first
            matched_row = next((r for r in rows if r.scope.strip().lower() == cleaned_req_scope), None)
            # 2. Try substring match
            if not matched_row:
                matched_row = next(
                    (r for r in rows if cleaned_req_scope in r.scope.strip().lower() or r.scope.strip().lower() in cleaned_req_scope),
                    None
                )
            # 3. Try word prefix sharing (prefix of length >= 3)
            if not matched_row:
                def get_prefixes(text_str):
                    return [w[:4] for w in text_str.lower().split() if len(w) >= 3]
                
                req_prefixes = get_prefixes(cleaned_req_scope)
                for r in rows:
                    row_prefixes = get_prefixes(r.scope)
                    if any(p in row_prefixes for p in req_prefixes):
                        matched_row = r
                        break
        
        if not matched_row:
            # Match closest scope tier by quantity
            matched_row = min(rows, key=lambda r: abs(r.quantity - requested_qty))

        base_price = float(matched_row.base_price)

    # 3. Apply location multiplier
    LOCATION_MULTIPLIERS = {
        "colombo": 1.30,
        "gampaha": 1.20,
        "kandy": 1.15,
        "kalutara": 1.10,
        "galle": 1.10,
        "matara": 1.05,
        "jaffna": 1.05,
        "kurunegala": 1.00,
        "anuradhapura": 0.95,
        "badulla": 0.95
    }
    
    district_norm = str(district or "").strip().lower()
    multiplier = LOCATION_MULTIPLIERS.get(district_norm, 1.00)
    final_price = base_price * multiplier

    # 4. Round to the nearest 50 LKR
    rounded_price = round(final_price / 50.0) * 50
    return int(rounded_price)

