"""Seed HireHub database from seeders/data JSON files (20 rows per entity)."""

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
        print("Seed complete — 20 example rows loaded per entity from seeders/data/.")
        print("Sample login: sarah.mitchell@example.com / Password123 (employer)")
        print("Sample admin:  nadia.hassan@example.com / Password123 (community admin on C1)")


if __name__ == "__main__":
    seed()
