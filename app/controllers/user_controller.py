from flask import jsonify

from app.extensions import db
from app.models.user_model import User
from app.utils.cloudinary_client import upload_image


def _validate_user_payload(data, user_id=None):
    errors = []
    if not user_id:
        if not data.get("email"):
            errors.append("email is required.")
        if not data.get("full_name"):
            errors.append("full_name is required.")
    elif "full_name" in data and not str(data.get("full_name", "")).strip():
        errors.append("full_name is required.")
    return errors


def get_users():
    users = User.query.all()
    return jsonify({"users": [u.to_dict(include_stats=True) for u in users]}), 200


def get_user(user_id, current_user_id=None, current_user_role=None):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    is_admin = current_user_role == "admin"
    is_self = current_user_id == user_id
    if not is_admin and not is_self:
        return jsonify({"error": "Forbidden."}), 403

    include_skills = is_admin and user.role == "user"
    data = user.to_dict(include_stats=True, include_skills=include_skills)

    if is_admin:
        from app.models.community_member_model import CommunityMember

        memberships = CommunityMember.query.filter_by(user_id=user_id).all()
        data["community_memberships"] = []
        for membership in memberships:
            row = membership.to_dict()
            if membership.community:
                row["community"] = {
                    "id": membership.community.id,
                    "name": membership.community.name,
                }
            data["community_memberships"].append(row)

    return jsonify({"user": data}), 200


def update_user(user_id, data, current_user_id, current_user_role=None):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    is_admin = current_user_role == "admin"
    is_self = user.id == current_user_id

    if "is_active" in data and not is_admin:
        return jsonify({"error": "Forbidden."}), 403

    if is_admin and not is_self:
        if set(data.keys()) - {"is_active"}:
            return jsonify({"error": "Admins may only change account status for other users."}), 403
    elif not is_self:
        return jsonify({"error": "Forbidden."}), 403

    errors = _validate_user_payload(data, user_id if is_self else user_id)
    if errors and is_self:
        return jsonify({"errors": errors}), 400

    if "is_active" in data and is_admin:
        user.is_active = bool(data["is_active"])

    if is_self:
        if "full_name" in data:
            user.full_name = str(data["full_name"]).strip()
        if "bio" in data:
            user.bio = data["bio"]
        if "location" in data:
            location = data["location"]
            user.location = location.strip() if isinstance(location, str) and location.strip() else None
        if "avatar_url" in data:
            user.avatar_url = data["avatar_url"]

    try:
        db.session.commit()
        return jsonify({"message": "User updated.", "user": user.to_dict(include_stats=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update user."}), 500


def upload_avatar(user_id, current_user_id, current_user_role, file_storage):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    is_admin = current_user_role == "admin"
    is_self = user.id == current_user_id
    if not is_admin and not is_self:
        return jsonify({"error": "Forbidden."}), 403

    try:
        avatar_url = upload_image(file_storage, "hirehub/users")
    except ValueError as exc:
        return jsonify({"errors": [str(exc)]}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        return jsonify({"error": "Failed to upload avatar."}), 500

    user.avatar_url = avatar_url
    try:
        db.session.commit()
        return jsonify({"message": "Avatar updated.", "user": user.to_dict(include_stats=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to save avatar."}), 500


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
