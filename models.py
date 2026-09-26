from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.sql import func
from database import Base

class Link(Base):
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True)
    plataforma = Column(String)
    id_produto_original = Column(String)
    link_afiliado_cache = Column(String, nullable=True)
    
    # === NOVAS COLUNAS PARA A VITRINE NETLIFY ===
    nome_produto = Column(String, nullable=True)
    imagem_url = Column(String, nullable=True)
    preco_oferta = Column(Float, nullable=True)
    # ============================================

    gerado_em = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    cliques = Column(Integer, default=0)

class RegistoClique(Base):
    __tablename__ = "registos_cliques"

    id = Column(Integer, primary_key=True, index=True)
    link_id = Column(Integer, ForeignKey("links.id"))
    data_hora = Column(DateTime(timezone=True), server_default=func.now())
    ip_usuario = Column(String)
    dispositivo = Column(String)
    origem = Column(String)