from app.extensions import db
from app.utils import utc_now


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    pricing = db.relationship("CategoryPricing", back_populates="category", lazy="dynamic")
    jobs = db.relationship("Job", back_populates="category", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
