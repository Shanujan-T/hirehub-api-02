from decimal import Decimal
import logging

from flask import jsonify

from app.extensions import db
from app.middleware import get_admin_community_ids, is_community_admin
from app.models.community_member_model import CommunityMember
from app.models.contract_application_model import ContractApplication
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.payment_model import Payment
from app.utils import utc_now
from app.utils.notification_utils import (
    notify_contract_assigned,
    notify_contract_application_rejected,
    notify_contract_open_internally,
    notify_deliverable_approved,
    notify_deliverable_forwarded,
    notify_deliverable_submitted,
)
from app.utils.pricing_utils import recalc_category_pricing

logger = logging.getLogger(__name__)


def _is_job_poster(user_id, contract):
    job = Job.query.get(contract.job_id)
    return job is not None and job.posted_by_id == user_id


def get_contracts(user_id, user_role):
    if user_role == "admin":
        contracts = Contract.query.all()
        return jsonify({"contracts": [c.to_dict(include_job=True, include_community=True) for c in contracts]}), 200

    seen = set()
    contracts = []

    def add_batch(batch):
        for c in batch:
            if c.id not in seen:
                seen.add(c.id)
                contracts.append(c)

    add_batch(Contract.query.join(Job).filter(Job.posted_by_id == user_id).all())

    admin_ids = get_admin_community_ids(user_id)
    if admin_ids:
        add_batch(Contract.query.filter(Contract.community_id.in_(admin_ids)).all())

    add_batch(Contract.query.filter_by(assigned_member_id=user_id).all())

    member_community_ids = [
        m.community_id
        for m in CommunityMember.query.filter_by(user_id=user_id, status="approved").all()
    ]
    if member_community_ids:
        open_for_member = [
            c
            for c in Contract.query.filter_by(status="open_internally").all()
            if c.community_id in member_community_ids
        ]
        add_batch(open_for_member)

    payload = []
    for c in contracts:
        is_poster = _is_job_poster(user_id, c)
        is_admin = is_community_admin(user_id, c.community_id)
        is_member = c.community_id in member_community_ids
        is_assigned = c.assigned_member_id == user_id
        strip_poster = not is_poster and not is_admin
        # Members need community name when browsing internal openings across multiple communities
        include_community = is_poster or is_admin or is_member or is_assigned
        payload.append(
            c.to_dict(
                include_job=True,
                strip_poster=strip_poster,
                include_community=include_community,
            )
        )
    return jsonify({"contracts": payload}), 200


def get_contract(contract_id, user_id, user_role):
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404

    is_poster = _is_job_poster(user_id, contract)
    strip_poster = not is_poster and not is_community_admin(user_id, contract.community_id)

    if user_role != "admin" and not is_poster:
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
            strip_poster=strip_poster,
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
    job = Job.query.get(contract.job_id)
    try:
        db.session.commit()
        if job:
            notify_contract_open_internally(contract.community_id, job.title, contract.id)
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
        job = Job.query.get(contract.job_id)
        job_title = job.title if job else "the contract"
        notify_contract_assigned(application.member_id, job_title, contract.id)
        for other in others:
            notify_contract_application_rejected(other.member_id, job_title, contract.id)
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
    job = Job.query.get(contract.job_id)
    try:
        db.session.commit()
        if job:
            notify_deliverable_submitted(contract.community_id, job.title, contract.id)
        return jsonify({"message": "Deliverable submitted.", "contract": contract.to_dict(strip_poster=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to submit deliverable."}), 500


def approve_deliverable_admin(contract_id, user_id):
    """Community admin QA — forwards to job poster for final approval."""
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    if not is_community_admin(user_id, contract.community_id):
        return jsonify({"error": "Forbidden."}), 403
    if contract.status != "submitted":
        return jsonify({"error": "No deliverable to review."}), 400
    job = Job.query.get(contract.job_id)
    try:
        db.session.commit()
        if job:
            notify_deliverable_forwarded(job.posted_by_id, job.title, contract.id)
        return jsonify({
            "message": "Deliverable forwarded to job poster.",
            "contract": contract.to_dict(include_job=True),
        }), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to approve deliverable."}), 500


def approve_deliverable_poster(contract_id, poster_user_id):
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    job = Job.query.get(contract.job_id)
    if not job or job.posted_by_id != poster_user_id:
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
        try:
            if contract.assigned_member_id:
                notify_deliverable_approved(contract.assigned_member_id, job.title, contract.id)
        except Exception:
            logger.exception(
                "Failed to notify member of deliverable approval contract_id=%s", contract_id
            )
        return jsonify({
            "message": "Deliverable approved. Payment released.",
            "contract": contract.to_dict(include_job=True),
            "payment": payment.to_dict(),
        }), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to approve deliverable."}), 500
