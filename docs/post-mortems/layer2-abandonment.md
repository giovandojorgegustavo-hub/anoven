# Post-mortem: Layer 2 Abandonment

**Fecha discovery**: 2026-06-23
**Status**: Cleanup ejecutado, action items en curso (Fase 2 del curso bitácora-port)
**Severity**: HIGH (silent rot ~30 días, sin user-facing impact en Layer 1)
**Autor**: Sandia (asistido por Claude Code en audit-pair mode)

---

## Resumen ejecutivo

Durante May 17-26 se preparó la infraestructura de una **segunda arquitectura** en el server `anoven` ("Layer 2 — Claude Code SSH per-user con canon/skills/agents compartidos"), creando symlinks en homes de ~19 users + systemd services + binarios.

Esos componentes esperaban directorios `/opt/anoven-shared/` y `/opt/anoven-anthropic-proxy/` que serían deployados en un **segundo paso**. El segundo paso nunca ocurrió.

Los servicios fallaron diariamente sin alertar a nadie por **~30 días**, descubierto en audit del 2026-06-23.

**User-facing impact**: cero. La web app (Layer 1, https://anoven.ai) siguió funcionando perfecto. Pero ~1325 symlinks rotos quedaron en homes de 19 users, services fallaban en silencio, y el server tenía una arquitectura "muerta" ocupando espacio mental.

---

## Timeline

| Fecha | Evento | Evidencia |
|---|---|---|
| May 17-24 | Symlinks creados en `.claude/` de 19+ users apuntando a `/opt/anoven-shared/*` y `/opt/gentleman-shared/*` | `stat /home/{user}/.claude/CLAUDE.md` muestra fecha de creación |
| May 21-26 | Systemd services + timers registrados: `anoven-canon-refresh.timer`, `anoven-rollup-tokens.timer` | `/etc/systemd/system/anoven-canon-refresh.timer` fecha mtime May 23 |
| (esperado) | Deploy de `/opt/anoven-shared/cms/canon-refresh/` con binarios + schemas | **NUNCA EJECUTADO** |
| (esperado) | Deploy de `/opt/anoven-anthropic-proxy/` con `rollup-tokens.py` + tabla `api_calls` en postgres | **NUNCA EJECUTADO** |
| May 23 → Jun 22 | Service `anoven-canon-refresh.service` falla weekly con `ModuleNotFoundError: lib.canon_schema` | `journalctl -u anoven-canon-refresh.service` muestra entries May 23, Jun 15, Jun 22 |
| May 21 → Jun 23 | Service `anoven-rollup-tokens.service` falla daily (busca `/opt/anoven-anthropic-proxy/rollup-tokens.py` inexistente) | systemctl unit reset state daily |
| 2026-06-23 | Audit completo descubre: 1325 symlinks rotos + 2 services failed + 3 drop-in dirs huérfanos + binario muerto + DB postgres `anoven` casi vacía + 150 `.bak` files acumulados | Output del audit en `ANOVEN-CURRENT-STATE.md` |
| 2026-06-23 | Cleanup ejecutado: todo lo de Layer 2 eliminado, Layer 1 intacto | Verificación post-cleanup en `ANOVEN-CURRENT-STATE.md` |

---

## Root cause analysis

### Primary (causa raíz)

**Deploy manual multi-step no atómico**.

El deployment fue dividido en pasos: "primero registramos los hooks y symlinks, después deployamos `/opt/anoven-shared/` con los binarios reales". El sistema **permitió** completar el paso 1 y olvidarse del paso 2, sin que ninguna validación lo bloqueara.

Si el deploy hubiera sido **atómico** (todo o nada — validar que dependencias existan antes de declarar success), ese estado roto **no podría haber existido** en producción.

### Secondary (multiplicador)

**Cero monitoring + cero alertas**.

Los services `anoven-canon-refresh` y `anoven-rollup-tokens` empezaron a fallar **inmediatamente** después de su registro. Pero los errores solo se escribían a `journalctl`. Nadie lee logs proactivamente.

Sin alerta, un fallo silencioso puede durar indefinidamente. En este caso: 30 días hasta que un audit accidental lo descubrió.

### Contributing factors

- **Sin git en el repo**: cero history de qué deploy ocurrió cuándo. Imposible reconstruir "qué pasos del rollout efectivamente se ejecutaron".
- **Sin staging environment**: no había forma de probar el rollout completo antes de aplicarlo en prod.
- **CLAUDE.md aspiracional**: documentaba la arquitectura **deseada** (incluyendo `/opt/anoven-shared/`). Cuando alguien lo lee, asume que esa infra existe. Nadie verificó el gap entre documentación e infraestructura real.

---

## Lessons learned

1. **Si un path aparece en config/código/symlinks, ese path TIENE QUE EXISTIR al final del deploy**. Sin esa validación, el deploy es teatro.
2. **Services failed sin alertas = rot silencioso por meses**. Si un service puede fallar y nadie se entera, eventualmente va a fallar y nadie se va a enterar — durante mucho tiempo.
3. **Deploy manual multi-step = siempre falta un step**. La única manera de garantizar consistencia es atomicidad.
4. **Documentación arquitectónica describe intención, no realidad**. Sin verificación constante, ambos divergen. CLAUDE.md describe lo que querés que exista; la única fuente de verdad sobre lo que existe es inspección del server.

---

## Action items

| # | Item | Owner | Status | Reference |
|---|---|---|---|---|
| 1 | Cleanup completo de Layer 2 (symlinks, services, binarios, .bak files, DB huérfana) | Sandia | DONE 2026-06-23 | Fase 1 del curso |
| 2 | Meter git en `anoven-app/` + remote en GitHub | Sandia | DONE 2026-06-23 | M1 del curso, commit `67bd186` |
| 3 | Build monitoring + alertas (chequeo de services, symlinks, app respondiendo) | Sandia | PENDING | M3 del curso |
| 4 | Deploy estandarizado atómico (`deploy.sh` con verify + rollback) | Sandia | PENDING | M4 del curso |
| 5 | Definir si CLAUDE.md es "ground truth" o "arquitectura objetivo" — y si es lo segundo, mantener un doc separado con realidad | Sandia | ONGOING | mantenido en `docs/` del repo |

---

## Apéndice: evidencia y reproducibilidad

Comandos del audit que descubrieron el problema (READ-ONLY):

```bash
# Symlinks rotos contados
ssh root@anoven 'find /home -xtype l -lname "*anoven-shared*" | wc -l'
# → 1305

# Failed services
ssh root@anoven 'systemctl --failed --no-legend'
# → anoven-canon-refresh.service, anoven-rollup-tokens.service

# Cuál es el path que esperaban los services
ssh root@anoven 'systemctl cat anoven-canon-refresh.service'
# Muestra Environment=PYTHONPATH=/opt/anoven-shared/cms/canon-refresh:...

# Si el path existe
ssh root@anoven 'ls -la /opt/anoven-shared/ 2>&1'
# → No such file or directory
```

Audit completo + estado actual del server en `ANOVEN-CURRENT-STATE.md` (en el directorio raíz del mentor anoven-software local).

---

**Este post-mortem se commitea al repo `anoven` para que cualquiera (vos, tu socia, futuros miembros del equipo, Claude en sesiones futuras) pueda referenciarlo como evidencia de qué pasó y por qué tenemos M3 + M4 pendientes en Fase 2 del curso.**
