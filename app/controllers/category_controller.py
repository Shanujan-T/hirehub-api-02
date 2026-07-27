from flask import jsonify

from app.extensions import db
from app.models.category_model import Category
from app.models.category_pricing_model import CategoryPricing
from app.utils.pricing_utils import get_pricing_suggestion, recalc_category_pricing


def _validate_category_payload(data):
    errors = []
    if not data.get("name"):
        errors.append("name is required.")
    return errors


def create_category(data):
    errors = _validate_category_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400
    if Category.query.filter_by(name=data["name"]).first():
        return jsonify({"error": "Category already exists."}), 409
    cat = Category(name=data["name"])
    db.session.add(cat)
    try:
        db.session.commit()
        return jsonify({"message": "Category created.", "category": cat.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to create category."}), 500


def get_categories():
    categories = Category.query.all()
    return jsonify({"categories": [c.to_dict() for c in categories]}), 200


def get_category(category_id):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    return jsonify({"category": cat.to_dict()}), 200


def update_category(category_id, data):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    if "name" in data:
        cat.name = data["name"]
    try:
        db.session.commit()
        return jsonify({"message": "Category updated.", "category": cat.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update category."}), 500


def delete_category(category_id):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    try:
        db.session.delete(cat)
        db.session.commit()
        return jsonify({"message": "Category deleted."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete category."}), 500


def pricing_suggestion(category_id, location):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    price = get_pricing_suggestion(category_id, location)
    return jsonify({"suggested_price": price, "location": location, "category_id": category_id}), 200


def seed_category_pricing(category_id, data):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    location = data.get("location")
    average_price = data.get("average_price", 0)
    sample_size = data.get("sample_size", 0)
    if not location:
        return jsonify({"errors": ["location is required."]}), 400

    pricing = CategoryPricing.query.filter_by(category_id=category_id, location=location).first()
    if pricing:
        pricing.average_price = average_price
        pricing.sample_size = sample_size
    else:
        pricing = CategoryPricing(
            category_id=category_id,
            location=location,
            average_price=average_price,
            sample_size=sample_size,
        )
        db.session.add(pricing)
    try:
        db.session.commit()
        return jsonify({"message": "Pricing seeded.", "category_pricing": pricing.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to seed pricing."}), 500


def recalc_pricing(category_id, location):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    pricing = recalc_category_pricing(category_id, location)
    return jsonify({"message": "Pricing recalculated.", "category_pricing": pricing.to_dict()}), 200
