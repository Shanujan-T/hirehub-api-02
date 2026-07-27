from decimal import Decimal

from flask import jsonify

from app.extensions import db
from app.middleware import get_admin_community_ids, is_community_admin
from app.models.community_member_model import CommunityMember
from app.models.contract_application_model import ContractApplication
from app.models.contract_model import Contract
from app.models.payment_model import Payment
from app.utils import utc_now
from app.utils.pricing_utils import recalc_category_pricing


def get_contracts(user_id, user_role):
    if user_role == "employer":
        from app.models.job_model import Job
        contracts = (
            Contract.query.join(Job).filter(Job.employer_id == user_id).all()
        )
        return jsonify({"contracts": [c.to_dict(include_job=True, include_community=True) for c in contracts]}), 200

    if user_role == "admin":
        contracts = Contract.query.all()
        return jsonify({"contracts": [c.to_dict(include_job=True, include_community=True) for c in contracts]}), 200

    admin_ids = get_admin_community_ids(user_id)
    if admin_ids:
        contracts = Contract.query.filter(Contract.community_id.in_(admin_ids)).all()
        return jsonify({"contracts": [c.to_dict(include_job=True, include_community=True) for c in contracts]}), 200

    # Member view
    member_contracts = Contract.query.filter_by(assigned_member_id=user_id).all()
    open_contracts = Contract.query.filter_by(status="open_internally").all()
    member_community_ids = [
        m.community_id
        for m in CommunityMember.query.filter_by(user_id=user_id, status="approved").all()
    ]
    open_for_member = [
        c for c in open_contracts if c.community_id in member_community_ids
    ]
    all_contracts = {c.id: c for c in member_contracts + open_for_member}
    return jsonify({
        "contracts": [
            c.to_dict(include_job=True, strip_employer=True) for c in all_contracts.values()
        ]
    }), 200


def get_contract(contract_id, user_id, user_role):
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404

    strip_employer = user_role == "user" and not is_community_admin(user_id, contract.community_id)

    if user_role == "employer":
        from app.models.job_model import Job
        job = Job.query.get(contract.job_id)
        if not job or job.employer_id != user_id:
            return jsonify({"error": "Forbidden."}), 403

    if user_role == "user":
        admin_ids = get_admin_community_ids(user_id)
        member_ids = [
            m.community_id
            for m in CommunityMember.query.filter_by(user_id=user_id, status="approved").all()
        ]
        is_assigned = contract.assigned_member_id == user_id
        is_admin = contract.community_id in admin_ids
        is_member = contract.community_id in member_ids
        if not (is_assigned or is_admin or (is_member and contract.status == "open_internally")):
            return jsonify({"error": "Forbidden."}), 403

    return jsonify({
        "contract": contract.to_dict(
            include_job=True,
            strip_employer=strip_employer,
            include_community=True,
        )
    }), 200


def open_contract_internally(contract_id, user_id):
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    if not is_community_admin(user_id, contract.community_id):
        return jsonify({"error": "Forbidden."}), 403
    if contract.status != "pending_assignment":
        return jsonify({"error": "Contract cannot be opened internally."}), 400
    contract.status = "open_internally"
    try:
        db.session.commit()
        return jsonify({"message": "Contract opened internally.", "contract": contract.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to open contract."}), 500


def select_member(contract_id, application_id, user_id):
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    if not is_community_admin(user_id, contract.community_id):
        return jsonify({"error": "Forbidden."}), 403
    if contract.status != "open_internally":
        return jsonify({"error": "Contract is not open for member selection."}), 400

    application = ContractApplication.query.get(application_id)
    if not application or application.contract_id != contract_id:
        return jsonify({"error": "Contract application not found."}), 404

    application.status = "selected"
    contract.assigned_member_id = application.member_id
    contract.status = "active"

    others = ContractApplication.query.filter(
        ContractApplication.contract_id == contract_id,
        ContractApplication.id != application_id,
    ).all()
    for other in others:
        other.status = "rejected"

    try:
        db.session.commit()
        return jsonify({"message": "Member selected.", "contract": contract.to_dict(include_job=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to select member."}), 500


def submit_deliverable(contract_id, user_id, data):
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    if contract.assigned_member_id != user_id:
        return jsonify({"error": "Forbidden."}), 403
    if contract.status != "active":
        return jsonify({"error": "Contract is not active."}), 400

    deliverable_url = data.get("deliverable_url")
    if not deliverable_url:
        return jsonify({"errors": ["deliverable_url is required."]}), 400

    contract.deliverable_url = deliverable_url
    contract.status = "submitted"
    try:
        db.session.commit()
        return jsonify({"message": "Deliverable submitted.", "contract": contract.to_dict(strip_employer=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to submit deliverable."}), 500


def approve_deliverable_admin(contract_id, user_id):
    """Community admin QA - marks ready for employer review."""
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    if not is_community_admin(user_id, contract.community_id):
        return jsonify({"error": "Forbidden."}), 403
    if contract.status != "submitted":
        return jsonify({"error": "No deliverable to review."}), 400
    # Status stays submitted until employer approves
    try:
        db.session.commit()
        return jsonify({"message": "Deliverable forwarded to employer.", "contract": contract.to_dict(include_job=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to approve deliverable."}), 500


def approve_deliverable_employer(contract_id, employer_id):
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    from app.models.job_model import Job
    job = Job.query.get(contract.job_id)
    if not job or job.employer_id != employer_id:
        return jsonify({"error": "Forbidden."}), 403
    if contract.status != "submitted":
        return jsonify({"error": "No deliverable to approve."}), 400

    contract.status = "completed"
    job.status = "closed"

    commission_amount = contract.total_amount * (contract.commission_percent / Decimal("100"))
    member_payout = contract.total_amount - commission_amount
    contract.commission_amount = commission_amount
    contract.member_payout = member_payout

    payment = Payment(
        contract_id=contract.id,
        total_amount=contract.total_amount,
        commission_amount=commission_amount,
        commission_recipient="admin",
        member_payout=member_payout,
        status="released",
        released_at=utc_now(),
    )
    db.session.add(payment)

    try:
        db.session.commit()
        recalc_category_pricing(job.category_id, job.location)
        return jsonify({
            "message": "Deliverable approved. Payment released.",
            "contract": contract.to_dict(include_job=True),
            "payment": payment.to_dict(),
        }), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to approve deliverable."}), 500
