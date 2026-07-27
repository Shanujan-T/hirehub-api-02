from app.extensions import db
from app.utils import utc_now


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    contract_id = db.Column(db.Integer, db.ForeignKey("contracts.id"), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(
        db.Enum("open", "resolved", "dismissed", name="report_status"),
        nullable=False,
        default="open",
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    reporter = db.relationship("User")
    contract = db.relationship("Contract")

    def to_dict(self):
        return {
            "id": self.id,
            "reporter_id": self.reporter_id,
            "contract_id": self.contract_id,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
