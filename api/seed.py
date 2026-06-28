"""
Idempotent seed script.
Run with: python seed.py
Creates admin user + reference disciplines and levels if they don't already exist.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.models.discipline import Discipline
from app.models.level import Level
from app.models.user import User, UserRole
from app.services.auth import hash_password

ADMIN_EMAIL = "admin@lms.internal"
ADMIN_PASSWORD = "Admin123!"

EMPLOYEE_EMAIL = "employee@lms.internal"
EMPLOYEE_PASSWORD = "Employee123!"

DISCIPLINES = [
    "Computer Science",
    "Mechanical Engineering",
    "Electrical Engineering",
    "Civil Engineering",
    "Chemical Engineering",
]

LEVELS = [
    {"code": "E4", "name": "Engineer I", "rank": 1},
    {"code": "E5", "name": "Engineer II", "rank": 2},
    {"code": "E6", "name": "Senior Engineer", "rank": 3},
    {"code": "E7", "name": "Principal Engineer", "rank": 4},
]


def seed() -> None:
    db = SessionLocal()
    try:
        # Disciplines
        for name in DISCIPLINES:
            if not db.query(Discipline).filter(Discipline.name == name).first():
                db.add(Discipline(name=name))
                print(f"  + Discipline: {name}")
            else:
                print(f"  = Discipline exists: {name}")

        # Levels
        for lv in LEVELS:
            if not db.query(Level).filter(Level.code == lv["code"]).first():
                db.add(Level(code=lv["code"], name=lv["name"], rank=lv["rank"]))
                print(f"  + Level: {lv['code']} ({lv['name']})")
            else:
                print(f"  = Level exists: {lv['code']}")

        db.flush()

        # Admin user
        existing_admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not existing_admin:
            admin = User(
                name="LMS Admin",
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                role=UserRole.admin,
                active=True,
                force_password_change=False,
            )
            db.add(admin)
            print(f"  + Admin user: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        else:
            print(f"  = Admin exists: {ADMIN_EMAIL}")

        # Demo employee user
        cs = db.query(Discipline).filter(Discipline.name == "Computer Science").first()
        e5 = db.query(Level).filter(Level.code == "E5").first()
        existing_emp = db.query(User).filter(User.email == EMPLOYEE_EMAIL).first()
        if not existing_emp:
            emp = User(
                name="Demo Employee",
                email=EMPLOYEE_EMAIL,
                password_hash=hash_password(EMPLOYEE_PASSWORD),
                role=UserRole.employee,
                discipline_id=cs.id if cs else None,
                level_id=e5.id if e5 else None,
                active=True,
                force_password_change=False,
            )
            db.add(emp)
            print(f"  + Employee user: {EMPLOYEE_EMAIL} / {EMPLOYEE_PASSWORD}")
        else:
            print(f"  = Employee exists: {EMPLOYEE_EMAIL}")

        db.commit()
        print("\nSeed complete.")
    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding database...")
    seed()
