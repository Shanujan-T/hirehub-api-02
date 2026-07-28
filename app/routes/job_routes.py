from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import job_controller
from app.middleware import roles_required
from app.models.user_model import User

jobs_bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


def _current_user():
    user = User.query.get(int(get_jwt_identity()))
    return user.id, user.role


@jobs_bp.route("", methods=["GET"])
@jwt_required()
def list_jobs():
    user_id, user_role = _current_user()
    return job_controller.get_jobs(user_id, user_role)


@jobs_bp.route("", methods=["POST"])
@roles_required("client", "admin")
def create_job():
    return job_controller.create_job(request.get_json() or {}, get_jwt_identity())


@jobs_bp.route("/<int:job_id>", methods=["GET"])
@jwt_required()
def get_job(job_id):
    user_id, user_role = _current_user()
    return job_controller.get_job(job_id, user_id, user_role)


@jobs_bp.route("/<int:job_id>", methods=["PUT"])
@roles_required("client")
def update_job(job_id):
    return job_controller.update_job(job_id, request.get_json() or {}, get_jwt_identity())


@jobs_bp.route("/<int:job_id>", methods=["DELETE"])
@roles_required("client")
def delete_job(job_id):
    return job_controller.delete_job(job_id, get_jwt_identity())
