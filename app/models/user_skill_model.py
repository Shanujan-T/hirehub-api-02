from app.extensions import db


class UserSkill(db.Model):
    __tablename__ = "user_skills"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), nullable=False)
    level = db.Column(
        db.Enum("beginner", "intermediate", "advanced", "expert", name="skill_level"),
        nullable=False,
        default="intermediate",
    )

    __table_args__ = (db.UniqueConstraint("user_id", "skill_id"),)

    user = db.relationship("User", back_populates="user_skills")
    skill = db.relationship("Skill", back_populates="user_skills")

    def to_dict(self):
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "skill_id": self.skill_id,
            "level": self.level,
        }
        if self.skill:
            data["skill"] = self.skill.to_dict()
        return data
