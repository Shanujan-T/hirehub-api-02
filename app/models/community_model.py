from app.extensions import db
from app.utils import utc_now


class Community(db.Model):
    __tablename__ = "communities"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(255), nullable=True)
    reputation_score = db.Column(db.Float, default=0.0, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    members = db.relationship("CommunityMember", back_populates="community", lazy="dynamic")
    open_calls = db.relationship("OpenCall", back_populates="community", lazy="dynamic")
    applications = db.relationship(
        "CommunityApplication", back_populates="community", lazy="dynamic"
    )
    contracts = db.relationship("Contract", back_populates="community", lazy="dynamic")

    def approved_member_count(self):
        return self.members.filter_by(status="approved").count()

    def to_dict(self, include_member_count=False):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "location": self.location,
            "reputation_score": self.reputation_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_member_count:
            data["member_count"] = self.approved_member_count()
        return data
