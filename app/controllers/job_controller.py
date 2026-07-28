from datetime import datetime
from decimal import Decimal

from flask import jsonify

from app.extensions import db
from app.middleware import community_meets_minimum, get_admin_community_ids
from app.models.job_model import Job
from app.utils.pricing_utils import get_pricing_suggestion


def _validate_job_payload(data):
    errors = []
    if not data.get("title"):
        errors.append("title is required.")
    if not data.get("description"):
        errors.append("description is required.")
    if not data.get("category_id"):
        errors.append("category_id is required.")
    if not data.get("location"):
        errors.append("location is required.")
    if not data.get("deadline"):
        errors.append("deadline is required.")
    if not data.get("final_price"):
        errors.append("final_price is required.")
    return errors


def create_job(data, client_id):
    errors = _validate_job_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400

    pricing = get_pricing_suggestion(data["category_id"], data["location"])
    suggested = pricing["average_price"]

    deadline = data["deadline"]
    if isinstance(deadline, str):
        deadline = datetime.fromisoformat(deadline).date()

    job = Job(
        client_id=client_id,
        category_id=data["category_id"],
        title=data["title"],
        description=data["description"],
        location=data["location"],
        deadline=deadline,
        suggested_price=Decimal(str(suggested)) if suggested is not None else None,
        final_price=Decimal(str(data["final_price"])),
        status="open",
    )
    db.session.add(job)
    try:
        db.session.commit()
        return jsonify({"message": "Job created.", "job": job.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to create job."}), 500


def get_jobs(user_id, user_role):
    if user_role == "client":
        jobs = Job.query.filter_by(client_id=user_id).all()
        return jsonify({"jobs": [j.to_dict() for j in jobs]}), 200

    if user_role == "admin":
        jobs = Job.query.all()
        return jsonify({"jobs": [j.to_dict() for j in jobs]}), 200

    admin_community_ids = get_admin_community_ids(user_id)
    eligible_community_ids = []
    for cid in admin_community_ids:
        if community_meets_minimum(cid):
            eligible_community_ids.append(cid)

    if not eligible_community_ids:
        return jsonify({"jobs": []}), 200

    jobs = Job.query.filter_by(status="open").all()
    return jsonify({"jobs": [j.to_dict(strip_client=True) for j in jobs]}), 200


def get_job(job_id, user_id=None, user_role=None, strip_client=False):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404

    if user_role == "client" and job.client_id != user_id:
        return jsonify({"error": "Forbidden."}), 403

    if user_role == "user":
        strip_client = True

    return jsonify({"job": job.to_dict(strip_client=strip_client)}), 200


def update_job(job_id, data, client_id):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.client_id != client_id:
        return jsonify({"error": "Forbidden."}), 403
    if job.status != "open":
        return jsonify({"error": "Cannot update a non-open job."}), 400

    for field in ("title", "description", "location"):
        if field in data:
            setattr(job, field, data[field])
    if "final_price" in data:
        job.final_price = Decimal(str(data["final_price"]))
    if "deadline" in data:
        deadline = data["deadline"]
        if isinstance(deadline, str):
            deadline = datetime.fromisoformat(deadline).date()
        job.deadline = deadline

    try:
        db.session.commit()
        return jsonify({"message": "Job updated.", "job": job.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update job."}), 500


def delete_job(job_id, client_id):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.client_id != client_id:
        return jsonify({"error": "Forbidden."}), 403
    try:
        db.session.delete(job)
        db.session.commit()
        return jsonify({"message": "Job deleted."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete job."}), 500
