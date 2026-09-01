from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker , declarative_base

<<<<<<< Updated upstream
DATABASE_URL = "sqlite:///./test.db"  # Example for SQLite, replace with your database URL
=======
DATABASE_URL = "postgresql://postgres:umar123@localhost:5432/cms_db"
>>>>>>> Stashed changes

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
