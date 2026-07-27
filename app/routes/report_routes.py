from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import report_controller
from app.middleware import roles_required

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@reports_bp.route("", methods=["GET"])
@roles_required("admin")
def list_reports():
    return report_controller.get_reports()


@reports_bp.route("", methods=["POST"])
@jwt_required()
def create_report():
    return report_controller.create_report(request.get_json() or {}, get_jwt_identity())


@reports_bp.route("/<int:report_id>", methods=["PUT"])
@roles_required("admin")
def update_report(report_id):
    return report_controller.update_report(report_id, request.get_json() or {})
