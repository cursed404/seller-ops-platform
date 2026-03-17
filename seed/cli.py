from app.infrastructure.db.session import SessionLocal
from seed.demo_data import seed_demo


def main() -> None:
    with SessionLocal() as session:
        seed_demo(session)


if __name__ == "__main__":
    main()

