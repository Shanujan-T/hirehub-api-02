"""Seed HireHub database from seeders/data JSON files."""

from app import create_app
from app.extensions import db
from seeders.loader import run_seed


def seed():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        run_seed(db.session)
        db.session.commit()
        print("Seed complete — example data loaded from seeders/data/.")
        print()
        print("Platform admin:  admin@hirehub.lk / Password123")
        print("Employer:        sarah.mitchell@example.com / Password123")
        print("Community admin: nadia.hassan@example.com / Password123  (PixelForge Web Dev)")
        print("Member:          priya.nair@example.com / Password123")


if __name__ == "__main__":
    seed()
