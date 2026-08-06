from flask import jsonify

from app.extensions import db
from app.models.report_model import Report


def create_report(data, reporter_id):
    if not data.get("reason"):
        return jsonify({"errors": ["reason is required."]}), 400
    report = Report(
        reporter_id=reporter_id,
        contract_id=data.get("contract_id"),
        reason=data["reason"],
    )
    db.session.add(report)
    try:
        db.session.commit()
        return jsonify({"message": "Report submitted.", "report": report.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to submit report."}), 500


def _report_dict(report: Report) -> dict:
    data = report.to_dict()
    if report.reporter:
        data["reporter"] = {
            "id": report.reporter.id,
            "full_name": report.reporter.full_name,
            "email": report.reporter.email,
        }
    if report.contract:
        data["contract"] = report.contract.to_dict(include_job=True, include_community=True)
    return data


def get_reports():
    reports = Report.query.order_by(Report.created_at.desc()).all()
    return jsonify({"reports": [_report_dict(r) for r in reports]}), 200


def get_report(report_id):
    report = Report.query.get(report_id)
    if not report:
        return jsonify({"error": "Report not found."}), 404
    return jsonify({"report": _report_dict(report)}), 200


def update_report(report_id, data):
    report = Report.query.get(report_id)
    if not report:
        return jsonify({"error": "Report not found."}), 404
    if "status" in data:
        report.status = data["status"]
    try:
        db.session.commit()
        return jsonify({"message": "Report updated.", "report": _report_dict(report)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update report."}), 500
