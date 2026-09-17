"""
store.py — Camada de negócio da Feira Tech dos Jovens da Vocação.

Todas as regras de validação e travas de segurança estão documentadas
inline com comentários explicativos. Nenhuma lógica de negócio deve
existir fora deste módulo.
"""

import csv
import hashlib
import hmac
import io
import os
import re
import secrets
import unicodedata
import uuid
from datetime import datetime

from database import Avaliacao, Engajamento, SessionLocal, Stand, Visitor

# ── Constantes ──────────────────────────────────────────────────────────────

# Cursos disponíveis na 1ª Feira Tech dos Jovens da Vocação
VALID_COURSES = {"webdesign", "programacao", "audiovisual", "ppt"}

# Perfis de visitante permitidos
VALID_PROFILES = {"aluno", "funcionario", "visitante_externo", "empresa"}

COURSE_LABELS = {
    "webdesign": "Web Design",
    "programacao": "Programação",
    "audiovisual": "Audiovisual",
    "ppt": "Preparação para o Trabalho",
}

PROFILE_LABELS = {
    "aluno": "Aluno Vocação",
    "funcionario": "Funcionário Vocação",
    "visitante_externo": "Visitante Externo",
    "empresa": "Empresa",
}


# ── Utilitários internos ────────────────────────────────────────────────────

def normalize_group(name: str) -> str:
    """
    Converte o nome do grupo em um slug comparável (minúsculas, sem
    acentos, sem caracteres especiais, espaços viram hífens).

    Exemplos:
        "Horta Inteligente"  → "horta-inteligente"
        "HORTA INTELIGENTE"  → "horta-inteligente"
        "Hôrta Inteliigente" → "horta-inteliigente"

    Essa normalização é a base da TRAVA DE UNICIDADE: dois nomes que
    representem o mesmo grupo produzem o mesmo slug, bloqueando o
    segundo cadastro via UNIQUE constraint no banco.
    """
    name = name.strip().lower()
    # Remove acentos via decomposição Unicode
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    # Mantém apenas letras, dígitos e espaços
    name = re.sub(r"[^a-z0-9\s]", "", name)
    # Substitui sequências de espaços por hífen
    name = re.sub(r"\s+", "-", name.strip())
    return name


def _hash_visitor(visitor_key: str) -> str:
    """SHA-256 da visitor_key gerada no browser. Nunca armazenamos a chave original."""
    return hashlib.sha256(visitor_key.encode()).hexdigest()


def _hash_code(code: str, salt: str) -> str:
    """Derivação PBKDF2-HMAC-SHA256 do código de acesso do expositor."""
    return hashlib.pbkdf2_hmac(
        "sha256", code.encode(), salt.encode(), 120_000
    ).hex()


def _verify_code(stand: Stand | None, access_code: str) -> bool:
    """
    Compara o código informado com o hash armazenado usando hmac.compare_digest
    para evitar ataques de timing.
    """
    if not stand or not access_code:
        return False
    expected = _hash_code(access_code, stand.code_salt)
    return hmac.compare_digest(expected, stand.code_hash)


def _public_stand(stand: Stand) -> dict:
    """Retorna apenas os campos públicos do stand (sem salt e hash)."""
    return {
        "id": stand.id,
        "name": stand.name,
        "course": stand.course,
        "group_id": stand.group_id,
        "created_at": stand.created_at,
    }


# ── Stands ──────────────────────────────────────────────────────────────────

def list_public_stands() -> list[dict]:
    with SessionLocal() as db:
        stands = db.query(Stand).order_by(Stand.created_at).all()
        return [_public_stand(s) for s in stands]


def get_public_stand(stand_id: str) -> dict | None:
    with SessionLocal() as db:
        stand = db.query(Stand).filter_by(id=stand_id).first()
        return _public_stand(stand) if stand else None


def create_stand(name: str, course: str) -> tuple[dict, str]:
    """
    Cadastra um novo stand.

    TRAVA DE SEGURANÇA 1 — Unicidade por grupo:
        Antes de inserir, calcula o group_id (slug normalizado) e verifica
        se já existe. Se existir, lança ValueError com mensagem amigável.
        Como reforço, a constraint UNIQUE no banco também impede duplicatas
        em cenários de race condition.

    Retorna: (stand_dict, access_code) onde access_code é exibido UMA
    única vez e depois nunca mais pode ser recuperado.
    """
    group_id = normalize_group(name)

    with SessionLocal() as db:
        # ── TRAVA 1: verificação prévia de unicidade ──
        existing = db.query(Stand).filter_by(group_id=group_id).first()
        if existing:
            raise ValueError(
                f"O grupo '{name}' já possui um stand cadastrado. "
                "Cada grupo pode ter apenas 1 stand na feira."
            )

        # Gera código de acesso aleatório de 6 dígitos (sem ambiguidades 0/O, 1/I)
        access_code = "".join(secrets.choice("23456789ABCDEFGHJKMNPQRSTUVWXYZ") for _ in range(6))
        salt = secrets.token_hex(16)

        stand = Stand(
            id=uuid.uuid4().hex[:12],
            name=name,
            group_id=group_id,
            course=course,
            code_salt=salt,
            code_hash=_hash_code(access_code, salt),
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        db.add(stand)
        try:
            db.commit()
        except Exception:
            # Captura IntegrityError do banco caso duas requisições simultâneas
            # passem pela verificação prévia (race condition extremamente raro).
            db.rollback()
            raise ValueError(
                f"O grupo '{name}' já possui um stand cadastrado."
            )

        db.refresh(stand)
        return _public_stand(stand), access_code


def authenticate_stand(stand_id: str, access_code: str) -> dict | None:
    with SessionLocal() as db:
        stand = db.query(Stand).filter_by(id=stand_id).first()
        return _public_stand(stand) if _verify_code(stand, access_code) else None


# ── Perfis de Visitante ─────────────────────────────────────────────────────

def save_visitor_profile(
    visitor_key: str,
    profile_type: str,
    curso_aluno: str | None = None,
    group_name: str | None = None,
) -> dict:
    """
    Salva ou atualiza o perfil do visitante.

    Para alunos, armazena também o slug normalizado do seu grupo
    (group_name → group_id slug), que será usado na trava de avaliação
    cruzada em start_visit().
    """
    visitor_hash = _hash_visitor(visitor_key)

    # Para alunos, normalizamos o nome do grupo para comparação posterior
    normalized_group = normalize_group(group_name) if (
        group_name and profile_type == "aluno"
    ) else None

    with SessionLocal() as db:
        visitor = db.query(Visitor).filter_by(visitor_hash=visitor_hash).first()
        if visitor:
            # Atualiza perfil existente
            visitor.profile_type = profile_type
            visitor.curso_aluno = curso_aluno if profile_type == "aluno" else None
            visitor.group_name = normalized_group
        else:
            visitor = Visitor(
                visitor_hash=visitor_hash,
                profile_type=profile_type,
                curso_aluno=curso_aluno if profile_type == "aluno" else None,
                group_name=normalized_group,
                created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
            db.add(visitor)
        db.commit()

    return {"ok": True, "profile_type": profile_type}


def get_visitor_profile(visitor_key: str) -> dict | None:
    visitor_hash = _hash_visitor(visitor_key)
    with SessionLocal() as db:
        v = db.query(Visitor).filter_by(visitor_hash=visitor_hash).first()
        if not v:
            return None
        return {
            "profile_type": v.profile_type,
            "curso_aluno": v.curso_aluno,
            "group_name": v.group_name,
        }


# ── Avaliações (Visitas) ────────────────────────────────────────────────────

def start_visit(stand_id: str, visitor_key: str) -> tuple[str | None, str | None]:
    """
    Inicia uma visita/avaliação.

    TRAVA DE OURO — Aluno não avalia o próprio stand:
        Se o visitante for um aluno (profile_type == 'aluno') e o slug
        normalizado do seu grupo (visitor.group_name) for idêntico ao
        group_id do stand, a visita é bloqueada com erro 'own_stand'.
        Essa verificação é feita em nível de aplicação, antes de qualquer
        escrita no banco.

    Outros retornos possíveis:
        ('visit_id', None)   → sucesso
        (None, 'not_found')  → stand inexistente
        (None, 'own_stand')  → TRAVA: aluno tentando avaliar próprio stand
        (None, 'duplicate')  → visitante já avaliou este stand
    """
    visitor_hash = _hash_visitor(visitor_key)

    with SessionLocal() as db:
        stand = db.query(Stand).filter_by(id=stand_id).first()
        if not stand:
            return None, "not_found"

        # ── TRAVA DE OURO: verificação de avaliação cruzada ──
        visitor = db.query(Visitor).filter_by(visitor_hash=visitor_hash).first()
        if visitor and visitor.profile_type == "aluno" and visitor.group_name:
            if visitor.group_name == stand.group_id:
                # Aluno tentando avaliar o próprio grupo — BLOQUEADO
                return None, "own_stand"

        # Verifica se já existe avaliação concluída para este stand
        completed = (
            db.query(Avaliacao)
            .filter_by(stand_id=stand_id, visitor_hash=visitor_hash)
            .filter(Avaliacao.finished_at.isnot(None))
            .first()
        )
        if completed:
            return None, "duplicate"

        # Reutiliza visita ativa (evita duplicar em caso de recarregamento)
        active = (
            db.query(Avaliacao)
            .filter_by(stand_id=stand_id, visitor_hash=visitor_hash)
            .filter(Avaliacao.finished_at.is_(None))
            .first()
        )
        if active:
            return active.id, None

        # Cria nova avaliação
        profile_type = visitor.profile_type if visitor else None
        visit_id = uuid.uuid4().hex

        db.add(
            Avaliacao(
                id=visit_id,
                stand_id=stand_id,
                visitor_hash=visitor_hash,
                profile_type=profile_type,
                started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        )
        db.commit()
        return visit_id, None


def finish_visit(
    visit_id: str, stand_id: str, visitor_key: str, stars: int
) -> tuple[dict | None, str | None]:
    """
    Finaliza uma visita registrando a nota e a duração.

    Retorna:
        ({'duration_seconds': int}, None) → sucesso
        (None, 'not_found')               → visita não encontrada / chave incorreta
        (None, 'duplicate')               → visita já finalizada anteriormente
    """
    visitor_hash = _hash_visitor(visitor_key)

    with SessionLocal() as db:
        avaliacao = (
            db.query(Avaliacao)
            .filter_by(id=visit_id, stand_id=stand_id, visitor_hash=visitor_hash)
            .first()
        )

        if not avaliacao:
            return None, "not_found"
        if avaliacao.finished_at:
            return None, "duplicate"

        finished_at = datetime.now().astimezone()
        started_at = datetime.fromisoformat(avaliacao.started_at)
        duration = max(1, min(int((finished_at - started_at).total_seconds()), 43_200))

        avaliacao.finished_at = finished_at.isoformat(timespec="seconds")
        avaliacao.duration_seconds = duration
        avaliacao.stars = stars
        db.commit()

        return {"duration_seconds": duration}, None


# ── Engajamentos (Shares e Apoios) ──────────────────────────────────────────

def _get_finished_visit(db, stand_id: str, visitor_hash: str) -> Avaliacao | None:
    """Retorna a avaliação finalizada mais recente do visitante neste stand."""
    return (
        db.query(Avaliacao)
        .filter_by(stand_id=stand_id, visitor_hash=visitor_hash)
        .filter(Avaliacao.finished_at.isnot(None))
        .order_by(Avaliacao.finished_at.desc())
        .first()
    )


def register_share(stand_id: str, visitor_key: str) -> bool:
    """
    Registra um compartilhamento. Exige que o visitante tenha concluído
    uma avaliação do stand antes de compartilhar.
    """
    visitor_hash = _hash_visitor(visitor_key)
    with SessionLocal() as db:
        stand = db.query(Stand).filter_by(id=stand_id).first()
        visit = _get_finished_visit(db, stand_id, visitor_hash)
        if not stand or not visit:
            return False
        db.add(
            Engajamento(
                id=uuid.uuid4().hex,
                stand_id=stand_id,
                visitor_hash=visitor_hash,
                type="share",
                created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        )
        db.commit()
        return True


def create_support(
    stand_id: str, visitor_key: str, message: str
) -> tuple[dict | None, str | None]:
    """
    Envia uma mensagem de apoio ao mural do stand.

    Requer:
      - Avaliação concluída (visit_required)
      - Máximo de 1 apoio por visitante por stand (duplicate)
    """
    visitor_hash = _hash_visitor(visitor_key)
    with SessionLocal() as db:
        stand = db.query(Stand).filter_by(id=stand_id).first()
        visit = _get_finished_visit(db, stand_id, visitor_hash)
        if not stand or not visit:
            return None, "visit_required"

        dup = (
            db.query(Engajamento)
            .filter_by(stand_id=stand_id, visitor_hash=visitor_hash, type="support")
            .first()
        )
        if dup:
            return None, "duplicate"

        support = Engajamento(
            id=uuid.uuid4().hex,
            stand_id=stand_id,
            visitor_hash=visitor_hash,
            type="support",
            message=message,
            stars=visit.stars,
            status="pending",
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        db.add(support)
        db.commit()
        return {"id": support.id, "status": support.status}, None


def public_wall(limit: int = 24) -> list[dict]:
    """Retorna os apoios aprovados mais recentes para o mural público."""
    with SessionLocal() as db:
        rows = (
            db.query(Engajamento, Stand)
            .join(Stand)
            .filter(
                Engajamento.type == "support",
                Engajamento.status == "approved",
            )
            .order_by(Engajamento.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": eng.id,
                "stand_id": eng.stand_id,
                "stand_name": stand.name,
                "message": eng.message,
                "stars": eng.stars,
                "created_at": eng.created_at,
            }
            for eng, stand in rows
        ]


def moderate_support(
    stand_id: str, engagement_id: str, access_code: str, action: str
) -> tuple[dict | None, str | None]:
    """Aprova ou rejeita um apoio pendente. Exige código de acesso válido do expositor."""
    with SessionLocal() as db:
        stand = db.query(Stand).filter_by(id=stand_id).first()
        # TRAVA: verifica código de acesso antes de qualquer modificação
        if not _verify_code(stand, access_code):
            return None, "unauthorized"

        support = (
            db.query(Engajamento)
            .filter_by(id=engagement_id, stand_id=stand_id, type="support")
            .first()
        )
        if not support:
            return None, "not_found"

        support.status = "approved" if action == "approve" else "rejected"
        support.moderated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        db.commit()
        return {"id": support.id, "status": support.status}, None


# ── Dashboard do Expositor ──────────────────────────────────────────────────

def dashboard(stand_id: str, access_code: str) -> dict | None:
    """
    Retorna métricas completas do stand para o expositor autenticado.
    Inclui breakdown por perfil de visitante.
    """
    with SessionLocal() as db:
        stand = db.query(Stand).filter_by(id=stand_id).first()
        # TRAVA: verifica código antes de retornar qualquer dado
        if not _verify_code(stand, access_code):
            return None

        avaliacoes = (
            db.query(Avaliacao)
            .filter_by(stand_id=stand_id)
            .filter(Avaliacao.finished_at.isnot(None))
            .all()
        )

        durations = [a.duration_seconds for a in avaliacoes if a.duration_seconds]
        ratings = [a.stars for a in avaliacoes if a.stars]
        distribution = {str(s): sum(1 for r in ratings if r == s) for s in range(1, 6)}

        # Breakdown de visitantes por perfil
        by_profile: dict[str, int] = {}
        for a in avaliacoes:
            pt = a.profile_type or "desconhecido"
            by_profile[pt] = by_profile.get(pt, 0) + 1

        recent = [
            {
                "finished_at": a.finished_at,
                "duration_seconds": a.duration_seconds,
                "stars": a.stars,
                "profile_type": a.profile_type,
            }
            for a in reversed(avaliacoes[-12:])
        ]

        engs = db.query(Engajamento).filter_by(stand_id=stand_id).all()
        pending_supports = [
            {
                "id": e.id,
                "message": e.message,
                "stars": e.stars,
                "created_at": e.created_at,
            }
            for e in engs
            if e.type == "support" and e.status == "pending"
        ]

        return {
            "stand": _public_stand(stand),
            "visitors": len(avaliacoes),
            "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
            "average_duration_seconds": round(sum(durations) / len(durations)) if durations else 0,
            "total_duration_seconds": sum(durations),
            "distribution": distribution,
            "by_profile": by_profile,
            "recent_visits": recent,
            "shares": sum(1 for e in engs if e.type == "share"),
            "approved_supports": sum(
                1 for e in engs if e.type == "support" and e.status == "approved"
            ),
            "pending_supports": list(reversed(pending_supports)),
        }


def export_visits_csv(stand_id: str, access_code: str) -> bytes | None:
    """Exporta as avaliações do stand em CSV. Exige código de acesso válido."""
    with SessionLocal() as db:
        stand = db.query(Stand).filter_by(id=stand_id).first()
        if not _verify_code(stand, access_code):
            return None

        avaliacoes = (
            db.query(Avaliacao)
            .filter_by(stand_id=stand_id)
            .filter(Avaliacao.finished_at.isnot(None))
            .order_by(Avaliacao.finished_at)
            .all()
        )

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["data_hora", "perfil", "estrelas", "duracao_segundos"])
        for a in avaliacoes:
            writer.writerow([a.finished_at, a.profile_type or "", a.stars, a.duration_seconds])
        # BOM UTF-8 para compatibilidade com Excel
        return buf.getvalue().encode("utf-8-sig")


# ── Dashboard Admin Global ──────────────────────────────────────────────────

def _verify_admin(password: str) -> bool:
    """
    Valida a senha de administrador usando hmac.compare_digest
    para evitar ataques de timing.
    """
    expected = os.environ.get("ADMIN_PASSWORD", "admin@feira2025")
    return hmac.compare_digest(password, expected)


def admin_dashboard(password: str) -> dict | None:
    """
    Retorna métricas globais da feira para o administrador.
    Inclui ranking de stands, breakdown por perfil e totais gerais.
    """
    if not _verify_admin(password):
        return None

    with SessionLocal() as db:
        all_stands = db.query(Stand).order_by(Stand.created_at).all()
        all_avaliacoes = (
            db.query(Avaliacao)
            .filter(Avaliacao.finished_at.isnot(None))
            .all()
        )

        # Breakdown global por perfil de visitante
        by_profile: dict[str, int] = {}
        for a in all_avaliacoes:
            pt = a.profile_type or "desconhecido"
            by_profile[pt] = by_profile.get(pt, 0) + 1

        # Ranking de stands por nota média
        leaderboard = []
        for stand in all_stands:
            stand_ratings = [
                a.stars for a in all_avaliacoes
                if a.stand_id == stand.id and a.stars
            ]
            stand_visitors = sum(1 for a in all_avaliacoes if a.stand_id == stand.id)
            avg = round(sum(stand_ratings) / len(stand_ratings), 2) if stand_ratings else 0
            leaderboard.append(
                {
                    "id": stand.id,
                    "name": stand.name,
                    "course": stand.course,
                    "visitors": stand_visitors,
                    "average_rating": avg,
                    "total_ratings": len(stand_ratings),
                }
            )
        leaderboard.sort(
            key=lambda x: (x["average_rating"], x["total_ratings"]),
            reverse=True,
        )

        all_ratings = [a.stars for a in all_avaliacoes if a.stars]
        total_shares = db.query(Engajamento).filter_by(type="share").count()
        total_supports = db.query(Engajamento).filter_by(type="support", status="approved").count()

        return {
            "total_stands": len(all_stands),
            "total_visitors": len(all_avaliacoes),
            "total_ratings": len(all_ratings),
            "global_average": round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else 0,
            "by_profile": by_profile,
            "total_shares": total_shares,
            "total_approved_supports": total_supports,
            "leaderboard": leaderboard,
        }


def admin_export_csv(password: str) -> bytes | None:
    """Exporta todos os dados da feira em CSV global."""
    if not _verify_admin(password):
        return None

    with SessionLocal() as db:
        rows = (
            db.query(Avaliacao, Stand)
            .join(Stand)
            .filter(Avaliacao.finished_at.isnot(None))
            .order_by(Avaliacao.finished_at)
            .all()
        )

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "data_hora", "stand", "curso", "perfil_visitante",
            "estrelas", "duracao_segundos",
        ])
        for a, stand in rows:
            writer.writerow([
                a.finished_at, stand.name, stand.course,
                a.profile_type or "", a.stars, a.duration_seconds,
            ])
        return buf.getvalue().encode("utf-8-sig")
