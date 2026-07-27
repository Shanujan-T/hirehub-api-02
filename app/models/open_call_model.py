from app.extensions import db
from app.utils import utc_now


class OpenCall(db.Model):
    __tablename__ = "open_calls"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    required_skills = db.Column(db.String(512), nullable=True)
    status = db.Column(
        db.Enum("open", "closed", name="open_call_status"),
        nullable=False,
        default="open",
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    community = db.relationship("Community", back_populates="open_calls")

    def to_dict(self):
        return {
            "id": self.id,
            "community_id": self.community_id,
            "title": self.title,
            "required_skills": self.required_skills,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
