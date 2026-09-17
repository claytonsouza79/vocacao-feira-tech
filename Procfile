# Procfile — Configuração para deploy no Render.com
#
# O Render.com injeta automaticamente a variável PORT.
# O gunicorn escuta em 0.0.0.0:$PORT conforme exigido pelo Render.
#
# Parâmetros:
#   --workers 2      → 2 processos worker (adequado para o plano gratuito do Render)
#   --threads 4      → 4 threads por worker (melhora concorrência com SQLite)
#   --timeout 120    → timeout de 120s (tolerante a operações de banco mais lentas)
#   --bind 0.0.0.0:$PORT → escuta em todas as interfaces na porta do Render
#
web: gunicorn app:app --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT
