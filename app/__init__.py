from flask import Flask, jsonify
from flask_cors import CORS
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.config import Config
from app.extensions import db, jwt
from app.models.user_model import User
from app.routes import register_blueprints


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)
    jwt.init_app(app)

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
            job_model,
            open_call_model,
            payment_model,
            report_model,
            review_model,
            skill_model,
            user_model,
            user_skill_model,
        )

        db.create_all()

    register_blueprints(app)
    return app
