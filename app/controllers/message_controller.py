from flask import jsonify

from app.controllers.conversation_controller import (
    can_access_contract_conversation,
    get_conversation_for_contract,
)
from app.extensions import db, socketio
from app.models.contract_model import Contract
from app.models.message_model import Message
from app.models.user_model import User
from app.utils import utc_now


def _conversation_room(conversation_id):
    return f"conversation_{conversation_id}"


def list_messages(contract_id, user_id):
    conversation, error = get_conversation_for_contract(contract_id, user_id)
    if error:
        return error

    messages = (
        Message.query.filter_by(conversation_id=conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    unread = (
        Message.query.filter_by(conversation_id=conversation.id, read_at=None)
        .filter(Message.sender_id != user_id)
        .all()
    )
    for message in unread:
        message.read_at = utc_now()
    if unread:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return jsonify({
        "conversation_id": conversation.id,
        "messages": [m.to_dict(include_sender=True) for m in messages],
    }), 200


def send_message(contract_id, user_id, data):
    content = (data or {}).get("content", "").strip()
    if not content:
        return jsonify({"errors": ["content is required."]}), 400

    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    if not can_access_contract_conversation(user_id, contract):
        return jsonify({"error": "Forbidden."}), 403

    conversation, error = get_conversation_for_contract(contract_id, user_id)
    if error:
        return error

    sender = User.query.get(user_id)
    if not sender:
        return jsonify({"error": "Unauthorized."}), 401

    message = Message(
        conversation_id=conversation.id,
        sender_id=user_id,
        content=content,
    )
    db.session.add(message)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to send message."}), 500

    payload = message.to_dict(include_sender=True)
    socketio.emit("new_message", payload, room=_conversation_room(conversation.id))
    return jsonify({"message": payload}), 201
