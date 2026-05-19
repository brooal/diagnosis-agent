from app.db.session import Base,engine
from app.harness import models as harness_models  # noqa: F401
from app.rag import models as rag_models  # noqa: F401

def init_db():
    Base.metadata.create_all(engine)

if __name__ == '__main__':
    init_db()
    print("database initialized")
