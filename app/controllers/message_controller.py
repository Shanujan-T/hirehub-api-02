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
from app.utils.notification_utils import notify_new_message


def _conversation_room(conversation_id):
    return f"conversation_{conversation_id}"


def _serialize_messages(messages, user_id):
    payload = []
    for message in messages:
        data = message.to_dict(include_sender=True, viewer_id=user_id)
        if data is not None:
            payload.append(data)
    return payload


def _get_message_if_participant(message_id, user_id):
    message = Message.query.get(message_id)
    if not message:
        return None, (jsonify({"error": "Message not found."}), 404)

    conversation = message.conversation
    if not conversation or not conversation.contract:
        return None, (jsonify({"error": "Conversation not found."}), 404)

    contract = conversation.contract
    if not can_access_contract_conversation(user_id, contract):
        return None, (jsonify({"error": "Forbidden."}), 403)

    return message, None


def _emit_message_updated(message):
    payload = message.to_dict(include_sender=True)
    socketio.emit(
        "message_updated",
        payload,
        room=_conversation_room(message.conversation_id),
    )


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
        .filter_by(deleted_for_everyone=False)
        .all()
    )
    for message in unread:
        if message.is_visible_to(user_id):
            message.read_at = utc_now()
    if unread:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return jsonify({
        "conversation_id": conversation.id,
        "messages": _serialize_messages(messages, user_id),
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

    payload = message.to_dict(include_sender=True, viewer_id=user_id)
    socketio.emit("new_message", payload, room=_conversation_room(conversation.id))
    notify_new_message(
        contract.id,
        contract.community_id,
        contract.job_id,
        user_id,
        sender.full_name,
        content,
    )
    return jsonify({"message": payload}), 201


def delete_message_for_me(message_id, user_id):
    message, error = _get_message_if_participant(message_id, user_id)
    if error:
        return error

    if message.deleted_for_everyone:
        return jsonify({"error": "Message was already deleted for everyone."}), 400

    if user_id == message.sender_id:
        message.deleted_for_sender = True
    else:
        message.deleted_for_receiver = True

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete message."}), 500

    return jsonify({"message": "Message deleted for you."}), 200


def delete_message_for_everyone(message_id, user_id):
    message, error = _get_message_if_participant(message_id, user_id)
    if error:
        return error

    if user_id != message.sender_id:
        return jsonify({"error": "Only the sender can delete a message for everyone."}), 403

    if message.deleted_for_everyone:
        payload = message.to_dict(include_sender=True)
        return jsonify({"message": payload}), 200

    message.deleted_for_everyone = True
    message.deleted_at = utc_now()

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete message for everyone."}), 500

    _emit_message_updated(message)
    payload = message.to_dict(include_sender=True)
    return jsonify({"message": payload}), 200
