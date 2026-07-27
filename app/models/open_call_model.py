from app.extensions import db
from app.utils import utc_now


class OpenCall(db.Model):
    __tablename__ = "open_calls"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    status = db.Column(
        db.Enum("open", "closed", name="open_call_status"),
        nullable=False,
        default="open",
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    community = db.relationship("Community", back_populates="open_calls")
    open_call_skills = db.relationship(
        "OpenCallSkill", back_populates="open_call", cascade="all, delete-orphan", lazy="dynamic"
    )

    def to_dict(self, include_skills=False):
        data = {
            "id": self.id,
            "community_id": self.community_id,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_skills:
            data["skills"] = [ocs.to_dict() for ocs in self.open_call_skills]
        return data
