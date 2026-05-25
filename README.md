# FlowPremium

<p align="center">
  <strong>🎬 Plataforma premium de streaming por episodios</strong><br>
  Series, temporadas, reproductor cinematográfico y panel de administración — estilo Netflix.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Flask-3.0+-000000?style=flat-square&logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/SQLAlchemy-ORM-DB3069?style=flat-square" alt="SQLAlchemy">
  <img src="https://img.shields.io/badge/Deploy-Render-46E3B7?style=flat-square" alt="Render">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License">
</p>

---

## Descripción

**FlowPremium** es una aplicación web de streaming modular donde los usuarios exploran series, compran episodios premium y reproducen contenido con progreso guardado. Incluye panel admin completo, API protegida para video, i18n (ES/EN) y diseño UI premium.

### Características principales

- Catálogo con hero, filas y “Continuar viendo”
- Episodios gratis y de pago con control de acceso
- Reproductor con progreso y API de streaming autenticada
- Admin: series, temporadas, episodios, pagos y subida de medios
- Portadas independientes por serie
- Listo para PostgreSQL y despliegue en [Render](DEPLOY_RENDER.md)

---

## Tecnologías

| Capa | Stack |
|------|--------|
| Backend | Flask, Flask-Login, Flask-SQLAlchemy |
| Base de datos | SQLite (dev) · PostgreSQL (producción) |
| Medios | Pillow, almacenamiento local protegido |
| Servidor | Gunicorn |
| Frontend | Jinja2, CSS/JS custom (estilo streaming premium) |
| Tests | pytest |
| Deploy | Render Blueprint (`render.yaml`) |

---

## Estructura del proyecto

```
flowpremium/
├── app.py                 # Application factory
├── config.py              # Config dev / producción
├── extensions.py
├── requirements.txt       # Dependencias producción
├── requirements-dev.txt   # + pytest
├── render.yaml            # Blueprint Render
├── Procfile
├── modules/streaming/     # Modelos, rutas, servicios
├── models/                # Usuario
├── routes/                # Autenticación
├── templates/             # Vistas Jinja2
├── static/                # CSS & JS
├── migrations/            # SQL de referencia
├── storage/streaming/     # Videos y portadas (gitignored)
├── tests/
└── docs/screenshots/      # Capturas del producto
```

---

## Instalación

### Requisitos

- Python 3.11+
- pip

### Pasos

```bash
# Clonar el repositorio
git clone https://github.com/TU_USUARIO/flowpremium.git
cd flowpremium

# Entorno virtual (recomendado)
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# Dependencias
pip install -r requirements-dev.txt

# Variables de entorno (opcional en local)
copy .env.example .env   # Windows
# cp .env.example .env    # Linux/macOS

# Base de datos y usuarios admin por defecto
set FLASK_APP=app.py
flask init-db
# o: python create_admin.py

# Ejecutar
python app.py
```

Abre **http://127.0.0.1:5000**

| Rol | Usuario | Contraseña |
|-----|---------|------------|
| Admin | `admin` | `admin123` |
| Manager | `manager` | `manager123` |

> Cambia estas contraseñas antes de usar en producción.

### Rutas útiles

| URL | Descripción |
|-----|-------------|
| `/streaming` | Catálogo público |
| `/login` | Inicio de sesión |
| `/admin/streaming` | Panel de administración |
| `/health` | Health check (deploy) |

### Pruebas

```bash
python -m pytest -v
```

### Despliegue en Render

Ver guía completa: **[DEPLOY_RENDER.md](DEPLOY_RENDER.md)**

---

## Screenshots

> Añade capturas en `docs/screenshots/` y enlázalas aquí tras el deploy.

| Vista | Archivo sugerido |
|-------|------------------|
| Home / catálogo | `docs/screenshots/home.png` |
| Reproductor | `docs/screenshots/player.png` |
| Panel admin | `docs/screenshots/admin.png` |
| Login | `docs/screenshots/login.png` |

```markdown
![Home](docs/screenshots/home.png)
![Player](docs/screenshots/player.png)
```

---

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `SECRET_KEY` | Clave Flask (obligatoria en producción) |
| `DATABASE_URL` | PostgreSQL en Render |
| `STORAGE_PATH` | Ruta del disco persistente |
| `FLASK_ENV` | `production` en Render |
| `SEED_DEFAULT_USERS` | `true` solo en primer deploy |

Copia `.env.example` como referencia.

---

## Copyright

© 2026 **FlowPremium**. Todos los derechos reservados.

Este proyecto se distribuye bajo la licencia [MIT](LICENSE).

Desarrollado con Flask · Despliegue en Render · UI premium para streaming por episodios.
