"""
database.py — Modelos SQLAlchemy para a Feira Tech dos Jovens da Vocação.

Suporta SQLite (padrão local e Render.com gratuito) e PostgreSQL
(Render.com Starter/Pro). A troca é feita apenas pela variável de
ambiente DATABASE_URL — o código da aplicação não muda.
"""

import os

# pyrefly: ignore [missing-import]
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

# ── Configuração do banco de dados ─────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///feira_tech.db")

# Render.com envia URLs no formato postgres://, mas SQLAlchemy 2.x
# exige postgresql://. Fazemos a correção automática aqui.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite precisa de check_same_thread=False para uso com Flask (multi-thread).
# Para PostgreSQL ou outros bancos, passamos um dicionário vazio.
_connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


# ── Modelo: Stand ──────────────────────────────────────────────────────────

class Stand(Base):
    """
    Representa o stand/projeto de um grupo.

    TRAVA DE UNICIDADE: a coluna `group_id` (slug normalizado do nome do grupo)
    possui constraint UNIQUE. Qualquer tentativa de cadastrar dois stands com
    nomes equivalentes — mesmo com grafias diferentes de maiúsculas, acentos ou
    espaços — será bloqueada no nível do banco de dados.
    """

    __tablename__ = "stands"

    id = Column(String(12), primary_key=True)
    name = Column(String(100), nullable=False)

    # UNIQUE constraint é a trava definitiva contra duplicatas de grupo.
    # O valor é gerado pela função normalize_group() em store.py.
    group_id = Column(String(200), nullable=False, unique=True)

    # Cursos da feira: webdesign | programacao | audiovisual | ppt
    course = Column(String(20), nullable=False)

    # O código de acesso nunca é salvo em texto plano:
    # armazenamos apenas o salt e o hash pbkdf2_hmac.
    code_salt = Column(String(32), nullable=False)
    code_hash = Column(String(128), nullable=False)

    created_at = Column(String(30), nullable=False)

    avaliacoes = relationship(
        "Avaliacao", back_populates="stand", cascade="all, delete-orphan"
    )
    engajamentos = relationship(
        "Engajamento", back_populates="stand", cascade="all, delete-orphan"
    )


# ── Modelo: Visitor ────────────────────────────────────────────────────────

class Visitor(Base):
    """
    Perfil do visitante, identificado pelo SHA-256 da visitor_key gerada
    no navegador. Nunca armazenamos a chave original.

    O campo `group_name` (slug do grupo do aluno) é a base da
    TRAVA DE OURO: se visitor.group_name == stand.group_id, o aluno
    não pode avaliar aquele stand.
    """

    __tablename__ = "visitors"

    # Chave primária: hash SHA-256 da visitor_key gerada no browser.
    visitor_hash = Column(String(64), primary_key=True)

    # Tipos: aluno | funcionario | visitante_externo | empresa
    profile_type = Column(String(20), nullable=False)

    # Preenchido apenas para alunos.
    # Valores: webdesign | programacao | audiovisual | ppt
    curso_aluno = Column(String(20), nullable=True)

    # Slug normalizado do grupo do aluno (usado na trava de avaliação cruzada).
    # Para não-alunos, é NULL.
    group_name = Column(String(200), nullable=True)

    created_at = Column(String(30), nullable=False)


# ── Modelo: Avaliacao ──────────────────────────────────────────────────────

class Avaliacao(Base):
    """
    Registra cada visita/avaliação: início, fim, duração e nota em estrelas.
    O `profile_type` é desnormalizado aqui para facilitar relatórios sem JOINs.
    """

    __tablename__ = "avaliacoes"

    id = Column(String(32), primary_key=True)
    stand_id = Column(String(12), ForeignKey("stands.id"), nullable=False)
    visitor_hash = Column(String(64), nullable=False)

    # Desnormalizado para relatórios de engajamento por perfil.
    profile_type = Column(String(20), nullable=True)

    # Nota de 1 a 5 estrelas (null enquanto a visita está em andamento).
    stars = Column(Integer, nullable=True)

    started_at = Column(String(30), nullable=False)
    finished_at = Column(String(30), nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    stand = relationship("Stand", back_populates="avaliacoes")


# ── Modelo: Engajamento ────────────────────────────────────────────────────

class Engajamento(Base):
    """
    Registra compartilhamentos (type='share') e mensagens de apoio
    (type='support') enviadas ao mural público.

    Apoios passam por moderação do expositor antes de aparecer no mural:
    status: pending → approved | rejected
    """

    __tablename__ = "engajamentos"

    id = Column(String(32), primary_key=True)
    stand_id = Column(String(12), ForeignKey("stands.id"), nullable=False)
    visitor_hash = Column(String(64), nullable=False)

    # Tipo de engajamento: share | support
    type = Column(String(10), nullable=False)

    # Preenchido apenas para type='support'
    message = Column(Text, nullable=True)
    stars = Column(Integer, nullable=True)

    # Fluxo de moderação: pending → approved | rejected
    status = Column(String(10), default="pending")

    created_at = Column(String(30), nullable=False)
    moderated_at = Column(String(30), nullable=True)

    stand = relationship("Stand", back_populates="engajamentos")


# ── Inicialização ──────────────────────────────────────────────────────────

def init_db() -> None:
    """Cria todas as tabelas caso ainda não existam. Seguro para re-execução."""
    Base.metadata.create_all(bind=engine)
