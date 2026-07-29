from app.extensions import db
from app.utils import utc_now


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    posted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(255), nullable=False)
    deadline = db.Column(db.Date, nullable=False)
    suggested_price = db.Column(db.Numeric(10, 2), nullable=True)
    final_price = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(
        db.Enum("open", "assigned", "closed", name="job_status"),
        nullable=False,
        default="open",
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    poster = db.relationship("User", back_populates="jobs")
    category = db.relationship("Category", back_populates="jobs")
    applications = db.relationship(
        "CommunityApplication", back_populates="job", lazy="dynamic"
    )
    contract = db.relationship("Contract", back_populates="job", uselist=False)

    def to_dict(self, include_poster=False, strip_poster=False):
        data = {
            "id": self.id,
            "category_id": self.category_id,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "suggested_price": float(self.suggested_price) if self.suggested_price else None,
            "final_price": float(self.final_price) if self.final_price else 0,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if not strip_poster:
            data["posted_by_id"] = self.posted_by_id
        if include_poster and self.poster and not strip_poster:
            data["poster"] = {
                "id": self.poster.id,
                "full_name": self.poster.full_name,
                "location": self.poster.location,
            }
        if self.category:
            data["category"] = self.category.to_dict()
        return data
