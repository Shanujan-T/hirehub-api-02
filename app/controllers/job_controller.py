from datetime import datetime

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.middleware import can_browse_job_marketplace, marketplace_access_block_reason
from app.models.category_model import Category
from app.models.community_application_model import CommunityApplication
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.user_model import User


def create_job():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    required = ["category_id", "title", "description", "location", "deadline", "final_price"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    category = Category.query.get(data["category_id"])
    if not category:
        return jsonify({"error": "Invalid category."}), 400

    try:
        deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid deadline format. Use YYYY-MM-DD."}), 400

    job = Job(
        posted_by_id=user_id,
        category_id=data["category_id"],
        title=data["title"],
        description=data["description"],
        location=data["location"],
        deadline=deadline,
        suggested_price=data.get("suggested_price"),
        final_price=data["final_price"],
        status="open",
    )
    db.session.add(job)
    db.session.commit()

    return jsonify({"message": "Job created.", "job": job.to_dict()}), 201


def get_jobs():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    marketplace = request.args.get("marketplace", "").lower() in ("1", "true", "yes")

    if marketplace:
        blocked = marketplace_access_block_reason(user_id)
        if blocked:
            message, code = blocked
            return (
                jsonify({"error": message, "code": code}),
                403,
            )
        query = Job.query.filter_by(status="open")
        jobs = query.order_by(Job.created_at.desc()).all()
        return jsonify({"jobs": [j.to_dict(include_poster=True) for j in jobs]}), 200

    if user and user.role == "admin":
        jobs = Job.query.order_by(Job.created_at.desc()).all()
        return jsonify({"jobs": [j.to_dict(include_poster=True) for j in jobs]}), 200

    jobs = (
        Job.query.filter_by(posted_by_id=user_id)
        .order_by(Job.created_at.desc())
        .all()
    )
    return jsonify({"jobs": [j.to_dict() for j in jobs]}), 200


def get_job(job_id):
    user_id = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404

    if job.posted_by_id == user_id:
        return jsonify({"job": job.to_dict(include_poster=True)}), 200

    if job.status == "open" and can_browse_job_marketplace(user_id):
        return jsonify({"job": job.to_dict(include_poster=True)}), 200

    return jsonify({"error": "Forbidden."}), 403


def update_job(job_id):
    user_id = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.posted_by_id != user_id:
        return jsonify({"error": "Forbidden."}), 403
    if job.status != "open":
        return jsonify({"error": "Only open jobs can be updated."}), 400

    data = request.get_json() or {}
    for field in ("title", "description", "location", "final_price", "suggested_price"):
        if field in data:
            setattr(job, field, data[field])
    if "deadline" in data:
        try:
            job.deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid deadline format."}), 400
    if "category_id" in data:
        if not Category.query.get(data["category_id"]):
            return jsonify({"error": "Invalid category."}), 400
        job.category_id = data["category_id"]

    db.session.commit()
    return jsonify({"message": "Job updated.", "job": job.to_dict()}), 200


def delete_job(job_id):
    user_id = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.posted_by_id != user_id:
        return jsonify({"error": "Forbidden."}), 403
    if job.status != "open":
        return jsonify({"error": "Only open jobs can be deleted."}), 400

    db.session.delete(job)
    db.session.commit()
    return jsonify({"message": "Job deleted."}), 200


def get_job_applications(job_id):
    user_id = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.posted_by_id != user_id:
        return jsonify({"error": "Forbidden."}), 403

    applications = (
        CommunityApplication.query.filter_by(job_id=job_id)
        .order_by(CommunityApplication.created_at.desc())
        .all()
    )
    return jsonify({"applications": [a.to_dict(include_community=True) for a in applications]}), 200
