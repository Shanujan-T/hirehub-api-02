from app.routes.auth_routes import auth_bp
from app.routes.category_routes import categories_bp
from app.routes.community_application_routes import community_applications_bp
from app.routes.community_member_routes import community_members_bp
from app.routes.community_routes import communities_bp
from app.routes.contract_application_routes import contract_applications_bp
from app.routes.contract_routes import contracts_bp
from app.routes.job_routes import jobs_bp
from app.routes.open_call_routes import open_calls_bp
from app.routes.payment_routes import payments_bp
from app.routes.report_routes import reports_bp
from app.routes.review_routes import reviews_bp
from app.routes.skill_routes import skills_bp
from app.routes.stats_routes import stats_bp
from app.routes.user_routes import users_bp
from app.routes.user_skill_routes import user_skills_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(skills_bp)
    app.register_blueprint(user_skills_bp)
    app.register_blueprint(communities_bp)
    app.register_blueprint(community_members_bp)
    app.register_blueprint(open_calls_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(community_applications_bp)
    app.register_blueprint(contracts_bp)
    app.register_blueprint(contract_applications_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(stats_bp)
