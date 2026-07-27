"""Seed demo data for LocalJobFinder viva demo."""

from datetime import date, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models.category_model import Category
from app.models.category_pricing_model import CategoryPricing
from app.models.community_member_model import CommunityMember
from app.models.community_model import Community
from app.models.job_model import Job
from app.models.skill_model import Skill
from app.models.user_model import User
from app.models.user_skill_model import UserSkill
from app.utils import utc_now


def seed():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        # Skills
        painting = Skill(name="Painting", category="Home Services")
        carpentry = Skill(name="Carpentry", category="Home Services")
        plumbing = Skill(name="Plumbing", category="Home Services")
        db.session.add_all([painting, carpentry, plumbing])
        db.session.flush()

        # Category
        category = Category(name="Door Painting")
        db.session.add(category)
        db.session.flush()

        CategoryPricing(
            category_id=category.id,
            location="Kandy",
            average_price=Decimal("45.00"),
            sample_size=12,
            last_updated=utc_now(),
        )

        # Employer: Nadia
        nadia = User(
            email="nadia@localjobs.test",
            full_name="Nadia",
            location="Kandy",
            role="employer",
        )
        nadia.set_password("Employer123")

        # Admin: Ruwan
        ruwan = User(
            email="ruwan@localjobs.test",
            full_name="Ruwan",
            location="Kandy",
            role="user",
        )
        ruwan.set_password("Admin123")

        # Members
        sam = User(email="sam@localjobs.test", full_name="Sam", location="Kandy", role="user")
        sam.set_password("Member123")
        dilan = User(email="dilan@localjobs.test", full_name="Dilan", location="Kandy", role="user")
        dilan.set_password("Member123")
        ishara = User(email="ishara@localjobs.test", full_name="Ishara", location="Kandy", role="user")
        ishara.set_password("Member123")

        db.session.add_all([nadia, ruwan, sam, dilan, ishara])
        db.session.flush()

        db.session.add_all([
            UserSkill(user_id=sam.id, skill_id=painting.id, level="advanced"),
            UserSkill(user_id=dilan.id, skill_id=carpentry.id, level="intermediate"),
            UserSkill(user_id=ishara.id, skill_id=plumbing.id, level="expert"),
        ])

        # Community
        community = Community(
            name="Kandy Home Services",
            description="Skilled home services community in Kandy",
            location="Kandy",
        )
        db.session.add(community)
        db.session.flush()

        db.session.add_all([
            CommunityMember(community_id=community.id, user_id=ruwan.id, role="admin", status="approved", joined_at=utc_now()),
            CommunityMember(community_id=community.id, user_id=sam.id, role="member", status="approved", joined_at=utc_now()),
            CommunityMember(community_id=community.id, user_id=dilan.id, role="member", status="approved", joined_at=utc_now()),
            CommunityMember(community_id=community.id, user_id=ishara.id, role="member", status="approved", joined_at=utc_now()),
        ])

        # Sample job
        job = Job(
            employer_id=nadia.id,
            category_id=category.id,
            title="Paint front door",
            description="Need the front door painted with weather-resistant paint.",
            location="Kandy",
            deadline=date.today() + timedelta(days=14),
            suggested_price=Decimal("45.00"),
            final_price=Decimal("50.00"),
            status="open",
        )
        db.session.add(job)

        db.session.commit()
        print("Seed complete!")
        print("Employer: nadia@localjobs.test / Employer123")
        print("Admin:    ruwan@localjobs.test / Admin123")
        print("Members:  sam@localjobs.test, dilan@localjobs.test, ishara@localjobs.test / Member123")


if __name__ == "__main__":
    seed()
