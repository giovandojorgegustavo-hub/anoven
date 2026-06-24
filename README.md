# Anoven

Monorepo de la app productiva de Anoven: backend FastAPI + frontend Next.js + migrations + docs operacionales.

**Producción**: https://anoven.ai
**Server**: `ssh anoven` (DigitalOcean, Ubuntu 24)

---

## Estructura

```
anoven-app/
├── backend/             # FastAPI (Python 3.12)
│   ├── app/             # main.py, routes/, services/, models/, schemas/
│   ├── migrations/      # SQL migrations (versionadas)
│   └── .venv/           # virtual env (gitignored)
├── frontend/            # Next.js 16 + React 19 + Tailwind 4
├── scripts/
│   ├── monitoring/      # check_health.sh + alerts Telegram
│   └── deploy/          # deploy.sh atómico con verify + rollback
└── docs/
    ├── post-mortems/    # análisis blameless de incidentes
    ├── monitoring/      # cómo opera el sistema de alertas
    └── deploy/          # cómo deployar + rollback
```

---

## Servicios deployados

| Servicio | Puerto | Status |
|---|---|---|
| `anoven-app-backend.service` | 8000 (local) | active |
| `anoven-app-frontend.service` | 3100 (local) | active |
| PostgreSQL | 5432 (local) | active — DB `anoven_app_dev` |
| Engram daemon | 7437 (local) | active |
| Caddy (HTTPS) | 443 | proxy a 3100 + 8000 |

---

## Cómo operar

| Acción | Comando |
|---|---|
| Deploy | `sudo ./scripts/deploy/deploy.sh` |
| Dry-run deploy | `sudo ./scripts/deploy/deploy.sh --dry-run` |
| Health check manual | `sudo ./scripts/monitoring/check_health.sh` |
| Ver log monitoring | `tail -f /var/log/anoven-monitoring.log` |
| Ver log deploy | `tail -f /var/log/anoven-deploy.log` |
| Logs servicios | `journalctl -u anoven-app-backend.service -f` |

---

## Setup nuevo (servidor desde cero)

Ver `docs/deploy/README.md`. Pre-requisitos:
- git, curl, psql, systemctl, npm
- `.env.monitoring` con bot Telegram configurado
- SSH key del server agregada al repo de GitHub
- venv de Python con deps backend
- `npm ci` en frontend

---

## Historia

Este repo nace el 2026-06-23 como resolución del action item #2 del post-mortem de Layer 2 (`docs/post-mortems/layer2-abandonment.md`). Antes vivía como código no versionado con backups manuales `.bak-pre-XXX-timestamp`.
