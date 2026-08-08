from app.extensions import db


class PricingReference(db.Model):
    __tablename__ = "pricing_references"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category = db.Column(db.String(255), nullable=False)
    scope = db.Column(db.String(255), nullable=False)
    unit = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    base_price = db.Column(db.Numeric(10, 2), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "scope": self.scope,
            "unit": self.unit,
            "quantity": self.quantity,
            "basePrice": float(self.base_price) if self.base_price else 0.0,
        }
