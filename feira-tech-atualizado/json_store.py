"""Persistência local da Feira Tech em um único arquivo JSON."""

import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import threading
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "feira_tech.json")
VALID_COURSES = {"python", "web", "audio", "outro"}
_lock = threading.RLock()


def _empty_data():
    return {"stands": [], "visitas": []}


def _save(data):
    temporary_path = f"{JSON_PATH}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary_path, JSON_PATH)


def _load():
    if not os.path.exists(JSON_PATH):
        _save(_empty_data())
    with open(JSON_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)
    data.setdefault("stands", [])
    data.setdefault("visitas", [])
    return data


def _find_stand(data, stand_id):
    return next((stand for stand in data["stands"] if stand["id"] == stand_id), None)


def _hash(value, salt):
    return hashlib.pbkdf2_hmac("sha256", value.encode(), salt.encode(), 120_000).hex()


def _public_stand(stand):
    return {
        "id": stand["id"],
        "name": stand["name"],
        "course": stand["course"],
        "created_at": stand["created_at"],
    }


def list_public_stands():
    with _lock:
        data = _load()
        return [_public_stand(stand) for stand in data["stands"]]


def get_public_stand(stand_id):
    with _lock:
        stand = _find_stand(_load(), stand_id)
        return _public_stand(stand) if stand else None


def create_stand(name, course):
    with _lock:
        data = _load()
        access_code = "".join(secrets.choice("23456789") for _ in range(6))
        salt = secrets.token_hex(16)
        stand = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "course": course,
            "code_salt": salt,
            "code_hash": _hash(access_code, salt),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        data["stands"].append(stand)
        _save(data)
        return _public_stand(stand), access_code


def verify_code(stand, access_code):
    if not stand or not access_code:
        return False
    expected = _hash(access_code, stand["code_salt"])
    return hmac.compare_digest(expected, stand["code_hash"])


def authenticate_stand(stand_id, access_code):
    with _lock:
        stand = _find_stand(_load(), stand_id)
        return _public_stand(stand) if verify_code(stand, access_code) else None


def start_visit(stand_id, visitor_key):
    with _lock:
        data = _load()
        stand = _find_stand(data, stand_id)
        if not stand:
            return None, "not_found"

        visitor_hash = hashlib.sha256(visitor_key.encode()).hexdigest()
        duplicate = next(
            (
                visit
                for visit in data["visitas"]
                if visit["stand_id"] == stand_id
                and visit.get("visitor_hash") == visitor_hash
                and visit.get("finished_at")
            ),
            None,
        )
        if duplicate:
            return None, "duplicate"

        active = next(
            (
                visit
                for visit in data["visitas"]
                if visit["stand_id"] == stand_id
                and visit.get("visitor_hash") == visitor_hash
                and not visit.get("finished_at")
            ),
            None,
        )
        if active:
            return active["id"], None

        visit_id = uuid.uuid4().hex
        data["visitas"].append(
            {
                "id": visit_id,
                "stand_id": stand_id,
                "stand_nome": stand["name"],
                "curso": stand["course"],
                "visitor_hash": visitor_hash,
                "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "finished_at": None,
                "duration_seconds": None,
                "stars": None,
            }
        )
        _save(data)
        return visit_id, None


def finish_visit(visit_id, stand_id, visitor_key, stars):
    with _lock:
        data = _load()
        visitor_hash = hashlib.sha256(visitor_key.encode()).hexdigest()
        visit = next(
            (
                item
                for item in data["visitas"]
                if item["id"] == visit_id
                and item["stand_id"] == stand_id
                and item.get("visitor_hash") == visitor_hash
            ),
            None,
        )
        if not visit:
            return None, "not_found"
        if visit.get("finished_at"):
            return None, "duplicate"

        finished_at = datetime.now().astimezone()
        started_at = datetime.fromisoformat(visit["started_at"])
        visit["finished_at"] = finished_at.isoformat(timespec="seconds")
        visit["duration_seconds"] = max(1, min(int((finished_at - started_at).total_seconds()), 43_200))
        visit["stars"] = stars
        _save(data)
        return dict(visit), None


def dashboard(stand_id, access_code):
    with _lock:
        data = _load()
        stand = _find_stand(data, stand_id)
        if not verify_code(stand, access_code):
            return None
        visits = [
            visit
            for visit in data["visitas"]
            if visit["stand_id"] == stand_id and visit.get("finished_at")
        ]
        durations = [visit["duration_seconds"] for visit in visits]
        ratings = [visit["stars"] for visit in visits]
        distribution = {str(star): ratings.count(star) for star in range(1, 6)}
        recent = [
            {
                "finished_at": visit["finished_at"],
                "duration_seconds": visit["duration_seconds"],
                "stars": visit["stars"],
            }
            for visit in reversed(visits[-12:])
        ]
        return {
            "stand": _public_stand(stand),
            "visitors": len(visits),
            "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
            "average_duration_seconds": round(sum(durations) / len(durations)) if durations else 0,
            "total_duration_seconds": sum(durations),
            "distribution": distribution,
            "recent_visits": recent,
        }


def export_visits_csv(stand_id, access_code):
    with _lock:
        data = _load()
        stand = _find_stand(data, stand_id)
        if not verify_code(stand, access_code):
            return None
        visits = [
            visit
            for visit in data["visitas"]
            if visit["stand_id"] == stand_id and visit.get("finished_at")
        ]
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["data_hora", "estrelas", "duracao_segundos"])
        for visit in visits:
            writer.writerow([visit["finished_at"], visit["stars"], visit["duration_seconds"]])
        return buffer.getvalue().encode("utf-8-sig")