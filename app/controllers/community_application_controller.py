from decimal import Decimal, InvalidOperation

from flask import jsonify

from app.extensions import db
from app.middleware import can_browse_job_marketplace, community_meets_minimum, get_admin_community_ids, is_community_admin
from app.models.community_application_model import CommunityApplication
from app.models.community_member_model import CommunityMember
from app.models.community_model import Community
from app.models.contract_model import Contract
from app.models.conversation_model import Conversation
from app.models.job_model import Job

MIN_COMMUNITY_MEMBERS = 3


def _validate_commission_percent(percent):
    if percent is None:
        return Decimal("3.0")
    pct = Decimal(str(percent))
    if pct < Decimal("2") or pct > Decimal("5"):
        return None
    return pct


def _validate_bid(data):
    proposed_cost = (data or {}).get("proposed_cost")
    proposed_days = (data or {}).get("proposed_days")
    if proposed_cost is None or proposed_days is None:
        return None, (jsonify({"errors": ["proposed_cost and proposed_days are required."]}), 400)
    try:
        cost = Decimal(str(proposed_cost))
        days = int(proposed_days)
    except (InvalidOperation, ValueError, TypeError):
        return None, (jsonify({"errors": ["proposed_cost and proposed_days must be valid numbers."]}), 400)
    if cost <= 0 or days <= 0:
        return None, (jsonify({"errors": ["proposed_cost and proposed_days must be greater than 0."]}), 400)
    note = (data or {}).get("note")
    if note is not None:
        note = str(note).strip() or None
    return (cost, days, note), None


def apply_to_job(job_id, community_id, user_id, data=None):
    if not can_browse_job_marketplace(user_id):
        return (
            jsonify(
                {
                    "error": "Job marketplace is available only to community admins "
                    "of communities with at least 3 approved members."
                }
            ),
            403,
        )

    bid, error = _validate_bid(data)
    if error:
        return error
    proposed_cost, proposed_days, note = bid

    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.status != "open":
        return jsonify({"error": "Job is not open for applications."}), 400
    if not is_community_admin(user_id, community_id):
        return jsonify({"error": "Forbidden."}), 403

    community = Community.query.get(community_id)
    if not community or community.status != "approved":
        return jsonify({"error": "Community must be approved before applying to jobs."}), 403

    if not community_meets_minimum(community_id):
        return jsonify({"error": f"Community must have at least {MIN_COMMUNITY_MEMBERS} approved members."}), 400

    existing = CommunityApplication.query.filter_by(
        job_id=job_id, community_id=community_id
    ).first()
    if existing:
        return jsonify({"error": "Community already applied to this job."}), 409

    application = CommunityApplication(
        job_id=job_id,
        community_id=community_id,
        status="applied",
        proposed_cost=proposed_cost,
        proposed_days=proposed_days,
        note=note,
    )
    db.session.add(application)
    try:
        db.session.commit()
        return jsonify({
            "message": "Applied to job.",
            "community_application": application.to_dict(include_community=True),
        }), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to apply to job."}), 500


def get_applications_for_job(job_id, poster_user_id):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.posted_by_id != poster_user_id:
        return jsonify({"error": "Forbidden."}), 403

    applications = CommunityApplication.query.filter_by(job_id=job_id).all()
    result = []
    for app in applications:
        app_data = app.to_dict(include_community=True)
        community = Community.query.get(app.community_id)
        if community:
            members = CommunityMember.query.filter_by(
                community_id=community.id, status="approved"
            ).all()
            app_data["community"]["members"] = [
                m.to_dict(include_user=True, include_user_skills=True) for m in members
            ]
        result.append(app_data)
    return jsonify({"community_applications": result}), 200


def get_my_applications(user_id):
    admin_ids = get_admin_community_ids(user_id)
    if not admin_ids:
        return jsonify({"community_applications": []}), 200
    applications = CommunityApplication.query.filter(
        CommunityApplication.community_id.in_(admin_ids)
    ).all()
    return jsonify({"community_applications": [a.to_dict(include_job=True) for a in applications]}), 200


def approve_community(application_id, poster_user_id, data=None):
    data = data or {}
    application = CommunityApplication.query.get(application_id)
    if not application:
        return jsonify({"error": "Community application not found."}), 404

    job = Job.query.get(application.job_id)
    if not job or job.posted_by_id != poster_user_id:
        return jsonify({"error": "Forbidden."}), 403
    if job.status != "open":
        return jsonify({"error": "Job is no longer open."}), 400

    application.status = "approved"
    job.status = "assigned"

    others = CommunityApplication.query.filter(
        CommunityApplication.job_id == job.id,
        CommunityApplication.id != application.id,
    ).all()
    for other in others:
        other.status = "rejected"

    commission_percent = _validate_commission_percent(data.get("commission_percent"))
    if commission_percent is None:
        return jsonify({"error": "commission_percent must be between 2 and 5."}), 400

    contract = Contract(
        job_id=job.id,
        community_id=application.community_id,
        total_amount=application.proposed_cost,
        commission_percent=commission_percent,
        status="pending_assignment",
    )
    db.session.add(contract)
    db.session.flush()

    conversation = Conversation(contract_id=contract.id)
    db.session.add(conversation)

    try:
        db.session.commit()
        return jsonify({
            "message": "Community approved. Contract created.",
            "community_application": application.to_dict(),
            "contract": contract.to_dict(include_job=True),
            "conversation": conversation.to_dict(),
        }), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to approve community."}), 500


def reject_community(application_id, poster_user_id):
    application = CommunityApplication.query.get(application_id)
    if not application:
        return jsonify({"error": "Community application not found."}), 404
    job = Job.query.get(application.job_id)
    if not job or job.posted_by_id != poster_user_id:
        return jsonify({"error": "Forbidden."}), 403
    application.status = "rejected"
    try:
        db.session.commit()
        return jsonify({"message": "Application rejected.", "community_application": application.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to reject application."}), 500
