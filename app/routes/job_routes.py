from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.controllers import job_controller

jobs_bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


@jobs_bp.route("", methods=["GET"])
@jwt_required()
def list_jobs():
    return job_controller.get_jobs()


@jobs_bp.route("", methods=["POST"])
@jwt_required()
def create_job():
    return job_controller.create_job()


@jobs_bp.route("/<int:job_id>", methods=["GET"])
@jwt_required()
def get_job(job_id):
    return job_controller.get_job(job_id)


@jobs_bp.route("/<int:job_id>", methods=["PUT"])
@jwt_required()
def update_job(job_id):
    return job_controller.update_job(job_id)


@jobs_bp.route("/<int:job_id>", methods=["DELETE"])
@jwt_required()
def delete_job(job_id):
    return job_controller.delete_job(job_id)


@jobs_bp.route("/<int:job_id>/applications", methods=["GET"])
@jwt_required()
def job_applications(job_id):
    return job_controller.get_job_applications(job_id)
