from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Aqui é onde trocamos o destino! Saímos do SQLite e vamos para o PostgreSQL
# Formato: postgresql://usuario:senha@localhost:porta/nome_do_banco
SQLALCHEMY_DATABASE_URL = "postgresql://neondb_owner:****************@ep-billowing-morning-b5d2is71-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

# Para PostgreSQL não precisamos do "check_same_thread" que o SQLite exigia
engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
