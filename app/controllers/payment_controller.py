from flask import jsonify

from app.middleware import get_admin_community_ids, is_community_admin
from app.models.contract_model import Contract
from app.models.payment_model import Payment


def get_payments(user_id, user_role):
    if user_role == "admin":
        payments = Payment.query.all()
        return jsonify({"payments": [p.to_dict() for p in payments]}), 200

    if user_role == "employer":
        from app.models.job_model import Job
        payments = (
            Payment.query.join(Contract).join(Job).filter(Job.employer_id == user_id).all()
        )
        return jsonify({"payments": [p.to_dict() for p in payments]}), 200

    # Community admin earnings (commission)
    admin_ids = get_admin_community_ids(user_id)
    if admin_ids:
        payments = Payment.query.join(Contract).filter(
            Contract.community_id.in_(admin_ids)
        ).all()
        return jsonify({"payments": [p.to_dict() for p in payments]}), 200

    # Member earnings
    payments = Payment.query.join(Contract).filter(
        Contract.assigned_member_id == user_id
    ).all()
    return jsonify({"payments": [p.to_dict() for p in payments]}), 200


def get_my_earnings(user_id, user_role):
    return get_payments(user_id, user_role)
