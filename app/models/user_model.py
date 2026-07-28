from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.utils import utc_now


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum("admin", "client", "user", name="user_role"),
        nullable=False,
        default="user",
    )
    full_name = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(255), nullable=True)
    avatar_url = db.Column(db.String(512), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user_skills = db.relationship("UserSkill", back_populates="user", lazy="dynamic")
    community_memberships = db.relationship(
        "CommunityMember", back_populates="user", lazy="dynamic"
    )
    jobs = db.relationship("Job", back_populates="client", lazy="dynamic")
    contract_applications = db.relationship(
        "ContractApplication", back_populates="member", lazy="dynamic"
    )
    assigned_contracts = db.relationship(
        "Contract",
        back_populates="assigned_member",
        foreign_keys="Contract.assigned_member_id",
        lazy="dynamic",
    )
    reviews_given = db.relationship(
        "Review",
        back_populates="reviewer",
        foreign_keys="Review.reviewer_id",
        lazy="dynamic",
    )
    sent_messages = db.relationship(
        "Message", back_populates="sender", lazy="dynamic"
    )

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def to_dict(self, include_stats=False, include_skills=False):
        data = {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "full_name": self.full_name,
            "bio": self.bio,
            "location": self.location,
            "avatar_url": self.avatar_url,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_skills:
            data["user_skills"] = [us.to_dict() for us in self.user_skills.all()]
        if include_stats:
            from app.models.contract_model import Contract

            completed = Contract.query.filter_by(
                assigned_member_id=self.id, status="completed"
            ).count()
            data["completed_project_count"] = completed
            from sqlalchemy import func
            from app.models.review_model import Review

            avg_rating = (
                db.session.query(func.avg(Review.rating))
                .filter(Review.member_id == self.id)
                .scalar()
            )
            data["rating"] = round(float(avg_rating), 2) if avg_rating else 0.0
        return data
