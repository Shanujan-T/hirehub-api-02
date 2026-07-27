from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import user_skill_controller

user_skills_bp = Blueprint("user_skills", __name__, url_prefix="/api/user-skills")


@user_skills_bp.route("", methods=["GET"])
@jwt_required()
def list_user_skills():
    user_id = request.args.get("user_id", type=int)
    return user_skill_controller.get_user_skills(user_id)


@user_skills_bp.route("", methods=["POST"])
@jwt_required()
def create_user_skill():
    return user_skill_controller.create_user_skill(request.get_json() or {})


@user_skills_bp.route("/<int:user_skill_id>", methods=["GET"])
@jwt_required()
def get_user_skill(user_skill_id):
    return user_skill_controller.get_user_skill(user_skill_id)


@user_skills_bp.route("/<int:user_skill_id>", methods=["PUT"])
@jwt_required()
def update_user_skill(user_skill_id):
    return user_skill_controller.update_user_skill(user_skill_id, request.get_json() or {})


@user_skills_bp.route("/<int:user_skill_id>", methods=["DELETE"])
@jwt_required()
def delete_user_skill(user_skill_id):
    return user_skill_controller.delete_user_skill(user_skill_id)
