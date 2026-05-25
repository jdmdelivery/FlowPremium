# Despliegue en Render

## Opción A: Blueprint (recomendado)

1. Sube el proyecto a **GitHub** (sin `.env`, sin `streaming.db`).
2. En [Render](https://render.com) → **New** → **Blueprint** → conecta el repo.
3. Render crea la base PostgreSQL, el Web Service, el disco persistente y las variables.

## Opción B: Manual

1. **PostgreSQL** → New Database → copia `Internal Database URL`.
2. **Web Service** → New → Python:
   - **Build:** `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start:** `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 120 app:app`
   - **Release:** `flask init-db`
   - **Health check path:** `/health`
3. **Environment:**
   - `FLASK_ENV=production`
   - `FLASK_APP=app.py`
   - `SECRET_KEY` → Generate
   - `DATABASE_URL` → URL de Postgres (Render la ajusta a `postgresql://`)
   - `STORAGE_PATH=/opt/render/project/src/storage/streaming`
4. **Disk** (10 GB): mount `/opt/render/project/src/storage` para que videos y portadas no se borren al redeploy.

## Después del deploy

- Cambia las contraseñas de `admin` y `manager` (creados por `flask init-db` si `SEED_DEFAULT_USERS=true`).
- Pon `SEED_DEFAULT_USERS=false` en producción tras el primer deploy.
- Admin: `https://tu-app.onrender.com/admin/streaming`

## Notas

- El plan **free** de Render apaga el servicio por inactividad (~50 s de arranque en frío).
- Subidas grandes: timeout de Gunicorn es 120 s; videos muy pesados pueden requerir plan de pago o almacenamiento externo (S3).
- Pruebas locales: `pip install -r requirements-dev.txt` y `python -m pytest -v`
