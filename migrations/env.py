from alembic import context
from sqlalchemy import create_engine

from app.config import DATABASE_URL
from app.models import Base

engine = create_engine(DATABASE_URL)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
