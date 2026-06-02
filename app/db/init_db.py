from app.db.session import Base,engine
from app.auto_diagnosis import models as auto_diagnosis_models  # noqa: F401
from app.harness import models as harness_models  # noqa: F401
from app.rag import models as rag_models  # noqa: F401

def init_db():
    Base.metadata.create_all(engine)

if __name__ == '__main__':
    init_db()
    print("database initialized")
