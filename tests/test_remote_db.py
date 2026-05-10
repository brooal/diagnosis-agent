# scripts/test_remote_db.py

from app.data_sources.remote_db import RemoteDB


def main():
    db = RemoteDB()
    result = db.ping()
    print(result)


if __name__ == "__main__":
    main()