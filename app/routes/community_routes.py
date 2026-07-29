from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request

from app.controllers import community_controller
from app.middleware import roles_required
from app.models.user_model import User

communities_bp = Blueprint("communities", __name__, url_prefix="/api/communities")


def _optional_current_user():
    verify_jwt_in_request(optional=True)
    identity = get_jwt_identity()
    if not identity:
        return None, None
    user = User.query.get(int(identity))
    if not user:
        return None, None
    return user.id, user.role


@communities_bp.route("", methods=["GET"])
def list_communities():
    _, role = _optional_current_user()
    status_filter = request.args.get("status")
    return community_controller.get_communities(role, status_filter)


@communities_bp.route("", methods=["POST"])
@jwt_required()
def create_community():
    return community_controller.create_community(request.get_json() or {}, get_jwt_identity())


@communities_bp.route("/<int:community_id>", methods=["GET"])
def get_community(community_id):
    user_id, role = _optional_current_user()
    return community_controller.get_community(community_id, user_id, role)


@communities_bp.route("/<int:community_id>", methods=["PUT"])
@jwt_required()
def update_community(community_id):
    return community_controller.update_community(community_id, request.get_json() or {}, get_jwt_identity())


@communities_bp.route("/<int:community_id>/review", methods=["PUT"])
@roles_required("admin")
def review_community(community_id):
    return community_controller.review_community(community_id, request.get_json() or {})


@communities_bp.route("/<int:community_id>/image", methods=["POST"])
@jwt_required()
def upload_community_image(community_id):
    file_storage = request.files.get("image")
    return community_controller.upload_community_image(
        community_id, get_jwt_identity(), file_storage
    )


@communities_bp.route("/<int:community_id>", methods=["DELETE"])
@jwt_required()
def delete_community(community_id):
    return community_controller.delete_community(community_id, get_jwt_identity())
