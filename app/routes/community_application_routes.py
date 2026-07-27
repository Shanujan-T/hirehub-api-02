from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import community_application_controller

community_applications_bp = Blueprint(
    "community_applications", __name__, url_prefix="/api/community-applications"
)


@community_applications_bp.route("/my", methods=["GET"])
@jwt_required()
def my_applications():
    return community_application_controller.get_my_applications(get_jwt_identity())


@community_applications_bp.route("/apply", methods=["POST"])
@jwt_required()
def apply_to_job():
    data = request.get_json() or {}
    return community_application_controller.apply_to_job(
        data.get("job_id"), data.get("community_id"), get_jwt_identity()
    )


@community_applications_bp.route("/job/<int:job_id>", methods=["GET"])
@jwt_required()
def job_applications(job_id):
    return community_application_controller.get_applications_for_job(job_id, get_jwt_identity())


@community_applications_bp.route("/<int:application_id>/approve", methods=["POST"])
@jwt_required()
def approve_community(application_id):
    return community_application_controller.approve_community(application_id, get_jwt_identity())


@community_applications_bp.route("/<int:application_id>/reject", methods=["POST"])
@jwt_required()
def reject_community(application_id):
    return community_application_controller.reject_community(application_id, get_jwt_identity())
