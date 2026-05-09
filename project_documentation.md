# Project Documentation — UNLZ Agent

Última actualización: 2026-05-08 (newbie-friendly rollout).

## Objetivo

App desktop orientada a agente local con opencode harness y llama.cpp local bundleado.

## Decisiones vigentes

1. Runtime cerrado:
- harness fijo `opencode`
- provider fijo `llamacpp`
- execution mode fijo `autonomous`

2. Distribución:
- instalador único NSIS
- incluye backend sidecar + runtime llama.cpp

3. Model serving:
- modelos no se bundlean
- modelos se autodescargan al primer arranque
- selección por hardware con plan JSON

4. Policy de modelo:
- estrategia MTP-first donde sea viable
- fallback automático por bucket
- en `gpu_24` se exige perfil `1_*`

5. Integridad:
- soporte SHA256 opcional por entrada de plan
- si hash no coincide, se descarta y fallback

6. UX newbie-first:
- UI por defecto en `simple`
- onboarding inicial con diagnóstico y autofix
- timeline SSE de etapas legibles para usuario final
- errores accionables (`human_message`, `common_causes`, `fix_steps`)

## Archivos clave

- `agent_server.py`: backend + bootstrap + policy de modelos
- `opencode_1_catalog.py`: parser de perfiles `1_*` desde OpenCode
- `tools/fill_model_sha256.py`: relleno automático de hashes
- `desktop/src/components/SettingsView.tsx`: UI bloqueada en settings críticos
- `desktop/src/components/OnboardingModal.tsx`: wizard inicial de 3 pasos
- `guardrails/validator.py`: traducción de errores técnicos a mensajes accionables
- `desktop/src-tauri/tauri.conf.json`: resources incluye `binaries/llama.cpp/**`
- `4_build_exe.bat`: sync de llama.cpp bundleado antes de compilar instalador

## Flujo de selección de modelo

1. Detectar VRAM/RAM.
2. Mapear a bucket.
3. Leer `UNLZ_HARDWARE_MODEL_PLAN_JSON`.
4. Seleccionar candidato principal.
5. Descargar modelo.
6. Verificar SHA256 si está definido.
7. Si falla, usar `fallback_candidates`.
8. Persistir resultado efectivo en `.env`.

## Variables nuevas relevantes

- `UNLZ_OPENCODE_PROFILES_FILE`
- `UNLZ_HARDWARE_MODEL_PLAN_JSON`
- `UNLZ_SELECTED_1_PROFILE`
- `UNLZ_BOOTSTRAP_TIER`
- `UNLZ_BOOTSTRAP_BUCKET`
- `UNLZ_MODEL_SOURCE_REPO`
- `UNLZ_MODEL_SOURCE_FILE`
- `UNLZ_MODEL_FALLBACK_INDEX`
- `UNLZ_MODEL_MTP_ACTIVE`

## Endpoints nuevos (newbie)

- `GET /health/onboarding`: checklist de estado inicial (provider, puertos, permisos, RAG)
- `POST /health/onboarding/fix`: autofix básico de runtime/carpetas
- `GET /newbie/task-templates`: plantillas de prompts guiados
- `GET /newbie/profile` y `POST /newbie/profile`: memoria de perfil de usuario
- `POST /newbie/snapshot`: snapshot de estado previo a acciones relevantes
- `GET /health/center`: panel de salud simplificado

## Contrato SSE extendido

Se agrega evento:
- `timeline`: `{ stage, label, ts }`

Evento `error` ahora puede incluir:
- `human_message`
- `common_causes`
- `fix_steps`

## Operación recomendada

1. Mantener `UNLZ_HARDWARE_MODEL_PLAN_JSON` como fuente única de truth.
2. Ejecutar script de hashes cuando cambien modelos/repos:

```powershell
.\venv\Scripts\python.exe tools\fill_model_sha256.py --env .env.example --models-dir "D:\Models\llamacpp" --write
```

3. Rebuild installer con:

```powershell
.\4_build_exe.bat
```

## Riesgos conocidos

- Repos HF de terceros pueden desaparecer o renombrar archivos.
- Buckets sin modelo local presente no pueden calcular hash hasta descargar.
- `gpu_24` falla intencionalmente si falta perfil `1_*` requerido.
