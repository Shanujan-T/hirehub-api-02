from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import user_controller
from app.middleware import roles_required
from app.models.user_model import User

users_bp = Blueprint("users", __name__, url_prefix="/api/users")


@users_bp.route("", methods=["GET"])
@roles_required("admin")
def list_users():
    return user_controller.get_users()


@users_bp.route("/<int:user_id>", methods=["GET"])
@jwt_required()
def get_user(user_id):
    current = User.query.get(int(get_jwt_identity()))
    return user_controller.get_user(user_id, current.id, current.role)


@users_bp.route("/<int:user_id>", methods=["PUT"])
@jwt_required()
def update_user(user_id):
    current = User.query.get(int(get_jwt_identity()))
    return user_controller.update_user(
        user_id, request.get_json() or {}, current.id, current.role
    )


@users_bp.route("/<int:user_id>/avatar", methods=["POST"])
@jwt_required()
def upload_avatar(user_id):
    current = User.query.get(int(get_jwt_identity()))
    file_storage = request.files.get("image")
    return user_controller.upload_avatar(user_id, current.id, current.role, file_storage)


@users_bp.route("/<int:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    return user_controller.delete_user(user_id, get_jwt_identity())
