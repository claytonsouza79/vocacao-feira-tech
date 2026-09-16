"""
Ponto de entrada para o Vercel.

O Vercel só executa o que está dentro de /api. Aqui a gente só importa
o app Flask que está na raiz do projeto (app.py) e expõe como "app" —
o runtime Python do Vercel (@vercel/python) sabe rodar qualquer objeto
WSGI chamado "app".
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401
