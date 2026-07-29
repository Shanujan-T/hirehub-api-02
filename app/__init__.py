import logging
import re
from collections import defaultdict

from flask import Flask, jsonify
from flask_cors import CORS
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.config import Config
from app.extensions import db, jwt, socketio
from app.models.user_model import User
from app.routes import register_blueprints

_GROUP_ORDER = [
    "auth",
    "users",
    "skills",
    "user_skills",
    "communities",
    "community_members",
    "open_calls",
    "categories",
    "category_pricing",
    "jobs",
    "community_applications",
    "contracts",
    "contract_applications",
    "payments",
    "reviews",
    "reports",
]

_METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}
_ALLOWED_METHODS = set(_METHOD_ORDER)
_EXCLUDED_ENDPOINTS = {"api_home", "static"}

_PRICING_PATH_MARKERS = ("/pricing-suggestion", "/seed-pricing", "/recalc-pricing")

_BLUEPRINT_DEFAULT_GROUP = {
    "auth": "auth",
    "users": "users",
    "skills": "skills",
    "user_skills": "user_skills",
    "communities": "communities",
    "community_members": "community_members",
    "open_calls": "open_calls",
    "jobs": "jobs",
    "community_applications": "community_applications",
    "contracts": "contracts",
    "contract_applications": "contract_applications",
    "payments": "payments",
    "reviews": "reviews",
    "reports": "reports",
}

_DESCRIPTIONS = {
    ("POST", "/api/auth/register"): "Register a new user account (role is always user)",
    ("POST", "/api/auth/login"): "Log in and receive a JWT access token",
    ("GET", "/api/auth/me"): "Get current authenticated user profile",
    ("GET", "/api/users"): "List users",
    ("GET", "/api/users/:id"): "Get a single user",
    ("PUT", "/api/users/:id"): "Update a user profile",
    ("POST", "/api/users/:id/avatar"): "Upload a user avatar image",
    ("POST", "/api/users/me/nic-document"): "Deprecated — NIC upload no longer used",
    ("POST", "/api/users/me/identity-verification"): "Deprecated — use OTP identity endpoints",
    ("POST", "/api/users/me/identity-verification/phone/send"): "Send SMS OTP for phone identity verification",
    ("POST", "/api/users/me/identity-verification/phone/confirm"): "Confirm phone OTP for identity verification",
    ("POST", "/api/users/me/identity-verification/email/send"): "Send email OTP for identity verification",
    ("POST", "/api/users/me/identity-verification/email/confirm"): "Confirm email OTP for identity verification",
    ("PUT", "/api/users/:id/identity-verification/review"): "Review identity verification (admin)",
    ("DELETE", "/api/users/:id"): "Delete a user",
    ("GET", "/api/skills"): "List all skills",
    ("POST", "/api/skills"): "Create a new skill",
    ("GET", "/api/skills/:id"): "Get a single skill",
    ("PUT", "/api/skills/:id"): "Update a skill",
    ("DELETE", "/api/skills/:id"): "Delete a skill",
    ("GET", "/api/user-skills"): "List user skills",
    ("POST", "/api/user-skills"): "Create a user skill link",
    ("GET", "/api/user-skills/:id"): "Get a user skill",
    ("PUT", "/api/user-skills/:id"): "Update a user skill",
    ("DELETE", "/api/user-skills/:id"): "Delete a user skill",
    ("GET", "/api/communities"): "List communities",
    ("POST", "/api/communities"): "Create a community",
    ("GET", "/api/communities/:id"): "Get a single community",
    ("PUT", "/api/communities/:id"): "Update a community",
    ("PUT", "/api/communities/:id/review"): "Review a community submission (admin)",
    ("POST", "/api/communities/:id/image"): "Upload a community image",
    ("DELETE", "/api/communities/:id"): "Delete a community",
    ("GET", "/api/community-members/my"): "List my community memberships",
    ("POST", "/api/community-members/join/:id"): "Request to join a community",
    ("GET", "/api/community-members/community/:id"): "List members of a community",
    ("POST", "/api/community-members/:id/approve"): "Approve a membership request",
    ("POST", "/api/community-members/:id/reject"): "Reject a membership request",
    ("DELETE", "/api/community-members/:id"): "Remove a community member",
    ("GET", "/api/open-calls"): "List open calls",
    ("POST", "/api/open-calls"): "Create an open call",
    ("GET", "/api/open-calls/:id"): "Get a single open call",
    ("PUT", "/api/open-calls/:id"): "Update an open call",
    ("DELETE", "/api/open-calls/:id"): "Delete an open call",
    ("GET", "/api/categories"): "List job categories",
    ("POST", "/api/categories"): "Create a category",
    ("GET", "/api/categories/:id"): "Get a single category",
    ("PUT", "/api/categories/:id"): "Update a category",
    ("DELETE", "/api/categories/:id"): "Delete a category",
    ("GET", "/api/categories/:id/pricing-suggestion"): "Get suggested price for category + location",
    ("POST", "/api/categories/:id/seed-pricing"): "Seed pricing data for a category",
    ("POST", "/api/categories/:id/recalc-pricing"): "Recalculate category pricing by location",
    ("GET", "/api/jobs"): "List jobs for current user",
    ("POST", "/api/jobs"): "Create a new job posting",
    ("GET", "/api/jobs/:id"): "Get a single job",
    ("PUT", "/api/jobs/:id"): "Update a job posting",
    ("DELETE", "/api/jobs/:id"): "Delete a job posting",
    ("GET", "/api/community-applications/my"): "List my community job applications",
    ("POST", "/api/community-applications/apply"): "Apply community to a job",
    ("GET", "/api/community-applications/job/:id"): "List applications for a job",
    ("POST", "/api/community-applications/:id/approve"): "Approve a community application",
    ("POST", "/api/community-applications/:id/reject"): "Reject a community application",
    ("GET", "/api/contracts"): "List contracts for current user",
    ("GET", "/api/contracts/:id"): "Get a single contract",
    ("POST", "/api/contracts/:id/open-internally"): "Open contract for internal hiring",
    ("POST", "/api/contracts/:id/select-member"): "Select a member for contract",
    ("POST", "/api/contracts/:id/submit-deliverable"): "Submit contract deliverable",
    ("POST", "/api/contracts/:id/admin-approve-deliverable"): "Admin approve submitted deliverable",
    ("POST", "/api/contracts/:id/poster-approve-deliverable"): "Job poster approve submitted deliverable",
    ("POST", "/api/contracts/:id/client-approve-deliverable"): "Legacy alias for poster-approve-deliverable",
    ("GET", "/api/contracts/:id/messages"): "List contract conversation messages",
    ("POST", "/api/contracts/:id/messages"): "Send a contract conversation message",
    ("GET", "/api/contract-applications/my"): "List my contract applications",
    ("POST", "/api/contract-applications/apply"): "Apply to an open contract",
    ("GET", "/api/contract-applications/contract/:id"): "List applications for a contract",
    ("GET", "/api/payments/my-earnings"): "Get my earnings summary",
    ("GET", "/api/payments"): "List payments for current user",
    ("GET", "/api/reviews"): "List reviews",
    ("POST", "/api/reviews"): "Create a contract review",
    ("GET", "/api/reports"): "List moderation reports",
    ("POST", "/api/reports"): "Submit a moderation report",
    ("PUT", "/api/reports/:id"): "Update a report status",
}


def _normalize_path(rule_path):
    return re.sub(r"<[^>]+>", ":id", rule_path)


def _group_for_rule(blueprint_name, path):
    if blueprint_name == "categories" and any(marker in path for marker in _PRICING_PATH_MARKERS):
        return "category_pricing"
    return _BLUEPRINT_DEFAULT_GROUP.get(blueprint_name, blueprint_name)


def _endpoint_description(method, path, endpoint):
    key = (method, path)
    if key in _DESCRIPTIONS:
        return _DESCRIPTIONS[key]
    action = endpoint.split(".")[-1].replace("_", " ")
    return action[:1].upper() + action[1:]


def _build_endpoint_index(app):
    grouped = defaultdict(list)
    seen = set()

    for rule in app.url_map.iter_rules():
        if rule.endpoint in _EXCLUDED_ENDPOINTS:
            continue

        blueprint_name = rule.endpoint.split(".")[0]
        path = _normalize_path(rule.rule)

        for method in sorted(rule.methods & _ALLOWED_METHODS, key=lambda m: _METHOD_ORDER[m]):
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)

            group = _group_for_rule(blueprint_name, path)
            grouped[group].append(
                {
                    "method": method,
                    "path": path,
                    "description": _endpoint_description(method, path, rule.endpoint),
                }
            )

    for group in grouped:
        grouped[group].sort(key=lambda entry: (_METHOD_ORDER[entry["method"]], entry["path"]))

    return {
        "api": "HireHub API",
        "version": "1.0",
        "endpoints": {group: grouped[group] for group in _GROUP_ORDER if group in grouped},
    }


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)
    jwt.init_app(app)
    socketio.init_app(app)

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        return User.query.get(int(identity))

    @app.errorhandler(OperationalError)
    @app.errorhandler(ProgrammingError)
    def handle_db_error(e):
        return jsonify({"error": "Database connection error.", "details": str(e)}), 503

    with app.app_context():
        from app.models import (  # noqa: F401
            category_model,
            category_pricing_model,
            community_application_model,
            community_member_model,
            community_model,
            contract_application_model,
            contract_model,
            conversation_model,
            job_model,
            message_model,
            open_call_model,
            open_call_skill_model,
            payment_model,
            report_model,
            review_model,
            skill_model,
            user_model,
            user_skill_model,
            verification_otp_model,
        )

        try:
            db.create_all()
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Database tables not initialized at startup: %s", exc
            )

    register_blueprints(app)

    from . import socket_events  # noqa: F401

    @app.route("/")
    def api_home():
        return _build_endpoint_index(app)

    return app
