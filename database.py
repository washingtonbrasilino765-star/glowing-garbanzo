import os
<<<<<<< HEAD
from dotenv import load_dotenv
=======

>>>>>>> 5e5191596b512985544da58cd721e02ff91c677c
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

<<<<<<< HEAD
# 1. Carrega as variáveis de ambiente declaradas no seu ficheiro .env
load_dotenv()

# 2. O módulo 'os' busca a chave DATABASE_URL dentro do .env
SQLALCHEMY_DATABASE_URL=os.getenv("DATABASE_URL")

# 3. Cria o motor de conexão com o banco de dados Neon
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# 4. Configura a sessão do banco de dados
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 5. Instância base para criação dos modelos/tabelas
Base = declarative_base()
=======

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise RuntimeError("DATABASE_URL não foi configurada no ambiente.")


engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()
>>>>>>> 5e5191596b512985544da58cd721e02ff91c677c
