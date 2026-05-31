from .config import get_settings
from .db import connect, init_db
from .demo_data import seed_demo_data


def main() -> None:
    settings = get_settings()
    init_db(settings.database_path)
    with connect(settings.database_path) as connection:
        seed_demo_data(connection)
    print(f"Initialized database at {settings.database_path}")


if __name__ == "__main__":
    main()

