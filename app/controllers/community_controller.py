from flask import jsonify

from app.extensions import db
from app.middleware import get_admin_community_ids
from app.models.community_member_model import CommunityMember
from app.models.community_model import Community
from app.utils import utc_now
from app.utils.cloudinary_client import upload_image


def _validate_community_payload(data):
    errors = []
    name = str(data.get("name", "")).strip()
    if not name:
        errors.append("name is required.")
    return errors, name


def create_community(data, user_id):
    errors, name = _validate_community_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400
    if Community.query.filter_by(name=name).first():
        return jsonify({"errors": ["Community name already exists."]}), 400

    description = data.get("description")
    if isinstance(description, str):
        description = description.strip() or None
    location = data.get("location")
    if isinstance(location, str):
        location = location.strip() or None

    community = Community(
        name=name,
        description=description,
        location=location,
    )
    db.session.add(community)
    db.session.flush()

    membership = CommunityMember(
        community_id=community.id,
        user_id=user_id,
        role="admin",
        status="approved",
        joined_at=utc_now(),
    )
    db.session.add(membership)
    try:
        db.session.commit()
        return jsonify({"message": "Community created.", "community": community.to_dict(include_member_count=True)}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to create community."}), 500


def get_communities():
    communities = Community.query.all()
    return jsonify({"communities": [c.to_dict(include_member_count=True) for c in communities]}), 200


def get_community(community_id):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404
    data = community.to_dict(include_member_count=True)
    members = CommunityMember.query.filter_by(
        community_id=community_id, status="approved"
    ).all()
    data["members"] = [m.to_dict(include_user=True, include_user_skills=True) for m in members]
    return jsonify({"community": data}), 200


def update_community(community_id, data, user_id):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404
    admin_ids = get_admin_community_ids(user_id)
    if community_id not in admin_ids:
        return jsonify({"error": "Forbidden."}), 403
    if "name" in data:
        community.name = data["name"]
    if "description" in data:
        community.description = data["description"]
    if "location" in data:
        community.location = data["location"]
    try:
        db.session.commit()
        return jsonify({"message": "Community updated.", "community": community.to_dict(include_member_count=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update community."}), 500


def delete_community(community_id, user_id):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404
    admin_ids = get_admin_community_ids(user_id)
    if community_id not in admin_ids:
        return jsonify({"error": "Forbidden."}), 403
    try:
        db.session.delete(community)
        db.session.commit()
        return jsonify({"message": "Community deleted."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete community."}), 500


def upload_community_image(community_id, user_id, file_storage):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404

    admin_ids = get_admin_community_ids(user_id)
    if community_id not in admin_ids:
        return jsonify({"error": "Forbidden."}), 403

    try:
        image_url = upload_image(file_storage, "hirehub/communities")
    except ValueError as exc:
        return jsonify({"errors": [str(exc)]}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        return jsonify({"error": "Failed to upload community image."}), 500

    community.image_url = image_url
    try:
        db.session.commit()
        return jsonify({
            "message": "Community image updated.",
            "community": community.to_dict(include_member_count=True),
        }), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to save community image."}), 500
