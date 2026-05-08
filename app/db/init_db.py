from app.db.session import Base,engine
from app.harness import models

def init_db():
    Base.metadata.create_all(engine)

if __name__ == '__main__':
    init_db()
    print("database initialized")
