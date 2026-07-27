from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models.category_pricing_model import CategoryPricing
from app.models.contract_model import Contract
from app.utils import utc_now


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


def get_pricing_suggestion(category_id, location):
    pricing = CategoryPricing.query.filter_by(
        category_id=category_id, location=location
    ).first()
    if pricing:
        return float(pricing.average_price)
    return 0.0
