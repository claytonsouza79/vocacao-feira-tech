"""
app.py — Servidor Flask da 1ª Feira Tech dos Jovens da Vocação.

Preparado para deploy no Render.com:
  - Lê a porta da variável de ambiente PORT (padrão: 5000)
  - Escuta em 0.0.0.0 (obrigatório para Render.com e outros PaaS)
  - Banco de dados via DATABASE_URL (SQLite local / PostgreSQL no Render)
  - Gunicorn como servidor WSGI de produção (via Procfile)
"""

import io
import os
import re

import qrcode
from flask import Flask, Response, jsonify, request, send_from_directory

import store

# Inicializa o banco de dados (cria tabelas se não existirem)
from database import init_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=None)

# Chave secreta para sessões Flask (gerada aleatoriamente em produção)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())

# Inicializa o banco na startup da aplicação
with app.app_context():
    init_db()


# ── Páginas (SPA) ──────────────────────────────────────────────────────────

@app.route("/")
@app.route("/visitar/<stand_id>")
@app.route("/expositor")
@app.route("/stand/<stand_id>")
@app.route("/admin")
def pages(stand_id=None):
    """Serve o SPA para todas as rotas de navegação."""
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, "static"), filename)


# ── API: Stands ────────────────────────────────────────────────────────────

@app.get("/api/stands")
def list_stands():
    return jsonify(store.list_public_stands())


@app.get("/api/stands/<stand_id>")
def get_stand(stand_id):
    stand = store.get_public_stand(stand_id)
    if not stand:
        return jsonify({"error": "Stand não encontrado."}), 404
    return jsonify(stand)


@app.post("/api/stands")
def create_stand():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    course = str(data.get("course") or "")

    # Validação de nome
    if not 3 <= len(name) <= 100:
        return jsonify({"error": "Informe um nome entre 3 e 100 caracteres."}), 400

    # Validação de curso
    if course not in store.VALID_COURSES:
        return jsonify({"error": f"Curso inválido. Escolha: {', '.join(store.VALID_COURSES)}"}), 400

    try:
        stand, access_code = store.create_stand(name, course)
    except ValueError as exc:
        # TRAVA 1: grupo já cadastrado
        return jsonify({"error": str(exc)}), 409

    return jsonify({"stand": stand, "access_code": access_code}), 201


@app.post("/api/stands/<stand_id>/access")
def access_stand(stand_id):
    data = request.get_json(silent=True) or {}
    access_code = str(data.get("access_code") or "")
    stand = store.authenticate_stand(stand_id, access_code)
    if not stand:
        return jsonify({"error": "Código inválido."}), 401
    return jsonify(stand)


# ── API: Perfis de Visitante ───────────────────────────────────────────────

@app.post("/api/visitors/profile")
def save_profile():
    data = request.get_json(silent=True) or {}
    visitor_key = str(data.get("visitor_key") or "")
    profile_type = str(data.get("profile_type") or "")
    curso_aluno = data.get("curso_aluno")
    group_name = str(data.get("group_name") or "").strip()

    # Validação de visitor_key
    if not re.fullmatch(r"[a-zA-Z0-9_-]{16,100}", visitor_key):
        return jsonify({"error": "Identificador de visitante inválido."}), 400

    # Validação de perfil
    if profile_type not in store.VALID_PROFILES:
        return jsonify({"error": f"Perfil inválido. Use: {', '.join(store.VALID_PROFILES)}"}), 400

    # Validações específicas para alunos
    if profile_type == "aluno":
        if curso_aluno not in store.VALID_COURSES:
            return jsonify({"error": "Informe o curso do aluno."}), 400
        if not 2 <= len(group_name) <= 100:
            return jsonify({"error": "Informe o nome do seu grupo (2–100 caracteres)."}), 400
    else:
        curso_aluno = None
        group_name = None

    result = store.save_visitor_profile(
        visitor_key=visitor_key,
        profile_type=profile_type,
        curso_aluno=curso_aluno,
        group_name=group_name or None,
    )
    return jsonify(result), 201


@app.get("/api/visitors/profile")
def get_profile():
    visitor_key = request.args.get("key", "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{16,100}", visitor_key):
        return jsonify({"error": "Identificador inválido."}), 400
    profile = store.get_visitor_profile(visitor_key)
    if not profile:
        return jsonify({"error": "Perfil não encontrado."}), 404
    return jsonify(profile)


# ── API: Avaliações (Visitas) ──────────────────────────────────────────────

@app.post("/api/stands/<stand_id>/visits/start")
def start_visit(stand_id):
    data = request.get_json(silent=True) or {}
    visitor_key = str(data.get("visitor_key") or "")

    if not re.fullmatch(r"[a-zA-Z0-9_-]{16,100}", visitor_key):
        return jsonify({"error": "Identificador de visita inválido."}), 400

    visit_id, error = store.start_visit(stand_id, visitor_key)

    if error == "not_found":
        return jsonify({"error": "Stand não encontrado."}), 404

    if error == "own_stand":
        # TRAVA DE OURO: aluno tentando avaliar o próprio stand
        return jsonify({
            "error": "Você não pode avaliar o stand do seu próprio grupo. "
                     "Visite os projetos dos outros grupos!",
            "own_stand": True,
        }), 403

    if error == "duplicate":
        return jsonify({
            "error": "Você já avaliou este stand neste dispositivo.",
            "duplicate": True,
        }), 409

    return jsonify({"visit_id": visit_id}), 201


@app.post("/api/stands/<stand_id>/visits/<visit_id>/finish")
def finish_visit(stand_id, visit_id):
    data = request.get_json(silent=True) or {}
    visitor_key = str(data.get("visitor_key") or "")

    try:
        stars = int(data.get("stars"))
    except (TypeError, ValueError):
        stars = 0

    if stars not in range(1, 6):
        return jsonify({"error": "Escolha uma nota de 1 a 5 estrelas."}), 400

    visit, error = store.finish_visit(visit_id, stand_id, visitor_key, stars)

    if error == "duplicate":
        return jsonify({"error": "Avaliação já registrada.", "duplicate": True}), 409
    if error:
        return jsonify({"error": "Visita não encontrada."}), 404

    return jsonify({"ok": True, "duration_seconds": visit["duration_seconds"]})


# ── API: Engajamentos ──────────────────────────────────────────────────────

@app.post("/api/stands/<stand_id>/engagement/share")
def register_share(stand_id):
    data = request.get_json(silent=True) or {}
    visitor_key = str(data.get("visitor_key") or "")

    if not re.fullmatch(r"[a-zA-Z0-9_-]{16,100}", visitor_key):
        return jsonify({"error": "Identificador inválido."}), 400

    if not store.register_share(stand_id, visitor_key):
        return jsonify({"error": "Conclua a avaliação antes de compartilhar."}), 403

    return jsonify({"ok": True}), 201


@app.post("/api/stands/<stand_id>/engagement/support")
def create_support(stand_id):
    data = request.get_json(silent=True) or {}
    visitor_key = str(data.get("visitor_key") or "")
    message = " ".join(str(data.get("message") or "").split())

    if data.get("consent") is not True:
        return jsonify({"error": "Confirme a autorização para enviar ao mural."}), 400

    if not re.fullmatch(r"[a-zA-Z0-9_-]{16,100}", visitor_key):
        return jsonify({"error": "Identificador inválido."}), 400

    if not 8 <= len(message) <= 180 or "<" in message or ">" in message:
        return jsonify({"error": "Escreva uma mensagem entre 8 e 180 caracteres."}), 400

    support, error = store.create_support(stand_id, visitor_key, message)

    if error == "duplicate":
        return jsonify({"error": "Você já enviou um apoio para este projeto."}), 409
    if error:
        return jsonify({"error": "Conclua a avaliação antes de enviar seu apoio."}), 403

    return jsonify(support), 201


@app.post("/api/stands/<stand_id>/engagement/<engagement_id>/moderate")
def moderate_support(stand_id, engagement_id):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "")

    if action not in {"approve", "reject"}:
        return jsonify({"error": "Ação inválida."}), 400

    result, error = store.moderate_support(
        stand_id, engagement_id, str(data.get("access_code") or ""), action
    )

    if error == "unauthorized":
        return jsonify({"error": "Código inválido."}), 401
    if error:
        return jsonify({"error": "Publicação não encontrada."}), 404

    return jsonify(result)


@app.get("/api/mural")
def public_wall():
    return jsonify(store.public_wall())


# ── API: Dashboard do Expositor ────────────────────────────────────────────

@app.get("/api/stands/<stand_id>/dashboard")
def stand_dashboard(stand_id):
    report = store.dashboard(stand_id, request.args.get("code", ""))
    if not report:
        return jsonify({"error": "Código inválido."}), 401
    return jsonify(report)


@app.get("/api/stands/<stand_id>/qr")
def stand_qr(stand_id):
    access_code = request.args.get("code", "")
    if not store.authenticate_stand(stand_id, access_code):
        return jsonify({"error": "Código inválido."}), 401

    visit_url = request.host_url.rstrip("/") + f"/visitar/{stand_id}"
    image = qrcode.make(visit_url)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return Response(
        output.getvalue(),
        mimetype="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/stands/<stand_id>/export")
def export_visits(stand_id):
    csv_bytes = store.export_visits_csv(stand_id, request.args.get("code", ""))
    if csv_bytes is None:
        return jsonify({"error": "Código inválido."}), 401
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="visitas-{stand_id}.csv"'
        },
    )


# ── API: Admin Global ──────────────────────────────────────────────────────

@app.get("/api/admin/dashboard")
def admin_dashboard():
    password = request.args.get("password", "")
    report = store.admin_dashboard(password)
    if not report:
        return jsonify({"error": "Senha de administrador inválida."}), 401
    return jsonify(report)


@app.get("/api/admin/export")
def admin_export():
    password = request.args.get("password", "")
    csv_bytes = store.admin_export_csv(password)
    if csv_bytes is None:
        return jsonify({"error": "Senha de administrador inválida."}), 401
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="feira-tech-completo.csv"'
        },
    )


# ── Inicialização local ────────────────────────────────────────────────────

if __name__ == "__main__":
    # Produção: gunicorn (via Procfile) define PORT e host.
    # Desenvolvimento local: usa porta 5000 por padrão.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)