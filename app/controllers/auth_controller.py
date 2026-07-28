from flask import jsonify
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models.user_model import User


def _validate_auth_payload(data, is_register=False):
    errors = []
    if is_register:
        if not data.get("email"):
            errors.append("email is required.")
        if not data.get("password"):
            errors.append("password is required.")
        if not data.get("full_name"):
            errors.append("full_name is required.")
        role = data.get("role", "user")
        if role not in ("user", "employer"):
            errors.append("role must be 'user' or 'employer'.")
    else:
        if not data.get("email"):
            errors.append("email is required.")
        if not data.get("password"):
            errors.append("password is required.")
    return errors


def register(data):
    errors = _validate_auth_payload(data, is_register=True)
    if errors:
        return jsonify({"errors": errors}), 400

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email already registered."}), 409

    user = User(
        email=data["email"],
        full_name=data["full_name"],
        role=data.get("role", "user"),
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"message": "Registered successfully.", "access_token": token, "user": user.to_dict()}), 201


def login(data):
    errors = _validate_auth_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400

    user = User.query.filter_by(email=data["email"]).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Invalid email or password."}), 401

    if not user.is_active:
        return jsonify({"error": "Account suspended."}), 403

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 200


def get_me(user_id):
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found."}), 404
    if not user.is_active:
        return jsonify({"error": "Account suspended."}), 403
    return jsonify({"user": user.to_dict(include_stats=True)}), 200
