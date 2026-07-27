from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import community_controller

communities_bp = Blueprint("communities", __name__, url_prefix="/api/communities")


@communities_bp.route("", methods=["GET"])
def list_communities():
    return community_controller.get_communities()


@communities_bp.route("", methods=["POST"])
@jwt_required()
def create_community():
    return community_controller.create_community(request.get_json() or {}, get_jwt_identity())


@communities_bp.route("/<int:community_id>", methods=["GET"])
def get_community(community_id):
    return community_controller.get_community(community_id)


@communities_bp.route("/<int:community_id>", methods=["PUT"])
@jwt_required()
def update_community(community_id):
    return community_controller.update_community(community_id, request.get_json() or {}, get_jwt_identity())


@communities_bp.route("/<int:community_id>", methods=["DELETE"])
@jwt_required()
def delete_community(community_id):
    return community_controller.delete_community(community_id, get_jwt_identity())
