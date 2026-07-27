from flask import jsonify

from app.extensions import db
from app.models.user_model import User


def _validate_user_payload(data, user_id=None):
    errors = []
    if not user_id:
        if not data.get("email"):
            errors.append("email is required.")
        if not data.get("full_name"):
            errors.append("full_name is required.")
    return errors


def get_users():
    users = User.query.all()
    return jsonify({"users": [u.to_dict(include_stats=True) for u in users]}), 200


def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify({"user": user.to_dict(include_stats=True)}), 200


def update_user(user_id, data, current_user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.id != current_user_id:
        return jsonify({"error": "Forbidden."}), 403

    errors = _validate_user_payload(data, user_id)
    if errors:
        return jsonify({"errors": errors}), 400

    if "full_name" in data:
        user.full_name = data["full_name"]
    if "bio" in data:
        user.bio = data["bio"]
    if "location" in data:
        user.location = data["location"]
    if "avatar_url" in data:
        user.avatar_url = data["avatar_url"]

    try:
        db.session.commit()
        return jsonify({"message": "User updated.", "user": user.to_dict(include_stats=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update user."}), 500


def delete_user(user_id, current_user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.id != current_user_id:
        return jsonify({"error": "Forbidden."}), 403
    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "User deleted."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete user."}), 500
