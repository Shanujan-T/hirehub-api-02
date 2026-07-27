from flask import jsonify

from app.extensions import db
from app.middleware import get_admin_community_ids, is_community_admin
from app.models.community_member_model import CommunityMember
from app.utils import utc_now


def request_join(community_id, user_id):
    existing = CommunityMember.query.filter_by(
        community_id=community_id, user_id=user_id
    ).first()
    if existing:
        return jsonify({"error": "Already requested or member."}), 409
    membership = CommunityMember(
        community_id=community_id,
        user_id=user_id,
        role="member",
        status="pending",
    )
    db.session.add(membership)
    try:
        db.session.commit()
        return jsonify({"message": "Join request submitted.", "community_member": membership.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to submit join request."}), 500


def get_community_members(community_id, status=None):
    query = CommunityMember.query.filter_by(community_id=community_id)
    if status:
        query = query.filter_by(status=status)
    members = query.all()
    return jsonify({"community_members": [m.to_dict(include_user=True) for m in members]}), 200


def get_my_memberships(user_id):
    memberships = CommunityMember.query.filter_by(user_id=user_id).all()
    return jsonify({"community_members": [m.to_dict() for m in memberships]}), 200


def approve_member(membership_id, admin_user_id, action):
    membership = CommunityMember.query.get(membership_id)
    if not membership:
        return jsonify({"error": "Community member not found."}), 404
    if not is_community_admin(admin_user_id, membership.community_id):
        return jsonify({"error": "Forbidden."}), 403
    if action == "approve":
        membership.status = "approved"
        membership.joined_at = utc_now()
    elif action == "reject":
        membership.status = "rejected"
    else:
        return jsonify({"error": "Invalid action."}), 400
    try:
        db.session.commit()
        return jsonify({"message": f"Member {action}d.", "community_member": membership.to_dict(include_user=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update membership."}), 500


def delete_community_member(membership_id, user_id):
    membership = CommunityMember.query.get(membership_id)
    if not membership:
        return jsonify({"error": "Community member not found."}), 404
    admin_ids = get_admin_community_ids(user_id)
    if membership.community_id not in admin_ids and membership.user_id != user_id:
        return jsonify({"error": "Forbidden."}), 403
    try:
        db.session.delete(membership)
        db.session.commit()
        return jsonify({"message": "Membership removed."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to remove membership."}), 500
