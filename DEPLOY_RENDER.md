# Despliegue en Render

## SQLite (por defecto, sin Postgres)

La app usa **SQLite** (`flowpremium.db`) si no defines `DATABASE_URL`. Ideal para el plan free sin base de datos externa.

> Monta un **disco persistente** en `/opt/render/project/src` para que `flowpremium.db` y los uploads no se borren en cada deploy.

## Opción A: Blueprint (recomendado)

1. Sube el proyecto a **GitHub** (sin `.env`, sin `*.db`).
2. En [Render](https://render.com) → **New** → **Blueprint** → conecta el repo.
3. Render crea el Web Service con disco y `SECRET_KEY` automático.

## PostgreSQL (opcional, futuro)

1. Crea **PostgreSQL** en Render y añade `DATABASE_URL` al Web Service.
2. La app detectará la URL y dejará de usar SQLite.

## Opción B: Manual

1. **Web Service** → New → Python:
   - **Build:** `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start:** `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 120 app:app`
   - **Release:** `flask init-db`
   - **Health check path:** `/health`
3. **Environment:**
   - `FLASK_ENV=production`
   - `FLASK_APP=app.py`
   - `SECRET_KEY` → Generate
   - `STORAGE_PATH=/opt/render/project/src/storage/streaming`
   - `DATABASE_URL` → *(opcional)* solo si usas Postgres
4. **Disk** (1+ GB): mount `/opt/render/project/src` para `flowpremium.db`, videos y portadas.

## Después del deploy

- Cambia las contraseñas de `admin` y `manager` (creados por `flask init-db` si `SEED_DEFAULT_USERS=true`).
- Pon `SEED_DEFAULT_USERS=false` en producción tras el primer deploy.
- Admin: `https://tu-app.onrender.com/admin/streaming`

## Notas

- El plan **free** de Render apaga el servicio por inactividad (~50 s de arranque en frío).
- Subidas grandes: timeout de Gunicorn es 120 s; videos muy pesados pueden requerir plan de pago o almacenamiento externo (S3).
- Pruebas locales: `pip install -r requirements-dev.txt` y `python -m pytest -v`
