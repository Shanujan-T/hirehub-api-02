from app.extensions import db
from app.utils import utc_now


class CommunityApplication(db.Model):
    __tablename__ = "community_applications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=False)
    status = db.Column(
        db.Enum("applied", "approved", "rejected", name="community_application_status"),
        nullable=False,
        default="applied",
    )
    applied_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (db.UniqueConstraint("job_id", "community_id"),)

    job = db.relationship("Job", back_populates="applications")
    community = db.relationship("Community", back_populates="applications")

    def to_dict(self, include_community=False, include_job=False):
        data = {
            "id": self.id,
            "job_id": self.job_id,
            "community_id": self.community_id,
            "status": self.status,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }
        if include_community and self.community:
            data["community"] = self.community.to_dict(include_member_count=True)
        if include_job and self.job:
            data["job"] = self.job.to_dict()
        return data
