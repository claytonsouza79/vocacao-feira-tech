"""Webserver local da Feira Tech: visitante e expositor."""

import io
import os
import re

import qrcode
from flask import Flask, Response, jsonify, request, send_from_directory

import json_store as store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=None)


@app.route("/")
@app.route("/visitar/<stand_id>")
@app.route("/expositor")
@app.route("/stand/<stand_id>")
def pages(stand_id=None):
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, "static"), filename)


@app.get("/api/stands")
def list_stands():
    return jsonify(store.list_public_stands())


@app.post("/api/stands")
def create_stand():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    course = str(data.get("course") or "outro")
    if not 3 <= len(name) <= 100:
        return jsonify({"error": "Informe um nome entre 3 e 100 caracteres."}), 400
    if course not in store.VALID_COURSES:
        course = "outro"
    stand, access_code = store.create_stand(name, course)
    return jsonify({"stand": stand, "access_code": access_code}), 201


@app.get("/api/stands/<stand_id>")
def get_stand(stand_id):
    stand = store.get_public_stand(stand_id)
    if not stand:
        return jsonify({"error": "Stand não encontrado."}), 404
    return jsonify(stand)


@app.post("/api/stands/<stand_id>/access")
def access_stand(stand_id):
    data = request.get_json(silent=True) or {}
    access_code = str(data.get("access_code") or "")
    stand = store.authenticate_stand(stand_id, access_code)
    if not stand:
        return jsonify({"error": "Código inválido."}), 401
    return jsonify(stand)


@app.post("/api/stands/<stand_id>/visits/start")
def start_visit(stand_id):
    data = request.get_json(silent=True) or {}
    visitor_key = str(data.get("visitor_key") or "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{16,100}", visitor_key):
        return jsonify({"error": "Identificador de visita inválido."}), 400
    visit_id, error = store.start_visit(stand_id, visitor_key)
    if error == "not_found":
        return jsonify({"error": "Stand não encontrado."}), 404
    if error == "duplicate":
        return jsonify({"error": "Este dispositivo já avaliou este stand.", "duplicate": True}), 409
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
    return Response(output.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/stands/<stand_id>/export")
def export_visits(stand_id):
    csv_bytes = store.export_visits_csv(stand_id, request.args.get("code", ""))
    if csv_bytes is None:
        return jsonify({"error": "Código inválido."}), 401
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="visitas-{stand_id}.csv"'},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)