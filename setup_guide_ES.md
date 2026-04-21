# Guía de Configuración (Desktop): UNLZ Agent

[🇬🇧 English](setup_guide.md) | [🇪🇸 Español](setup_guide_ES.md)

Esta guía describe el flujo recomendado actual: app desktop Tauri + `agent_server.py`.

## 1. Requisitos

- Windows 10/11
- Python 3.10+
- Node.js 18+
- Rust (toolchain de cargo)

## 2. Instalación inicial

Desde la raíz del repositorio:

```powershell
.\setup-desktop.ps1
```

El script:
- instala/verifica Rust
- crea `venv` e instala `requirements.txt`
- instala dependencias de `desktop/`
- prepara iconos Tauri si faltan
- crea `.env` desde `.env.example` si no existe

## 3. Configurar `.env`

En app instalada (setup NSIS), `.env` se guarda en la carpeta de instalación:
`<directorio de instalación>\\.env` (por defecto `C:\\Users\\<usuario>\\AppData\\Local\\UNLZ Agent\\.env`).

Ejemplo mínimo para llama.cpp:

```env
LLM_PROVIDER=llamacpp
AGENT_LANGUAGE=es
AGENT_EXECUTION_MODE=confirm
WEB_SEARCH_ENGINE=google
MINIMIZE_TO_TRAY_ON_CLOSE=false
WINDOW_CONTROLS_STYLE=windows
WINDOW_CONTROLS_SIDE=right
WINDOW_CONTROLS_ORDER=minimize,maximize,close
LLAMACPP_EXECUTABLE=C:\ruta\a\llama-server.exe
LLAMACPP_MODEL_PATH=C:\ruta\a\modelo.gguf
LLAMACPP_MODEL_ALIAS=mi-modelo
LLAMACPP_HOST=127.0.0.1
LLAMACPP_PORT=8080
```

## 4. Ejecutar

```powershell
.\start-desktop.ps1
```

Notas:
- `agent_server.py` escucha en `http://127.0.0.1:7719`
- el script limpia listeners stale en `1420` y `7719`

## 4.1 Build instalador único (.exe)

```powershell
.\3_build_exe.bat
```

Salida esperada:
- `dist-single-exe\UNLZ-Agent-Setup.exe`
- `UNLZ-Agent-Setup.exe` (copia directa en la raíz del repo)

Este instalador incluye modo offline para WebView2 y despliega internamente app + backend.
También muestra selector de idioma (Español/English) y usa `icon.ico` como ícono del setup.

## 5. Funciones clave para probar

- **Selector de modelos llama.cpp**:
  - dropdown con modelos `.gguf` detectados automáticamente
  - botón de carpeta para elegir `LLAMACPP_MODELS_DIR` desde explorador
  - botón de archivo para elegir `llama-server.exe` desde explorador
  - botón `Instalar/Actualizar llama.cpp` que instala o actualiza automáticamente y autoconfigura rutas base
  - ubicación por defecto: `<directorio de instalación>/llama.cpp` (modelos: `<directorio de instalación>/llama.cpp/models`)
  - botón `↻` para reanalizar si aparece un modelo nuevo con la app abierta
- **Modo Plan**: botón en chat (afecta primer envío)
- **Modo Iterador**: ejecución por etapas con validación
- **Carpetas**:
  - crear carpeta
  - asignar conversaciones
  - prompt de carpeta
  - documentos exclusivos de carpeta
- **Window Controls**:
  - estilo Windows/Mac
  - lado y orden configurables

## 6. Problemas comunes

- `network error` en chat:
  - revisar `agent_server.log`
  - reiniciar `start-desktop.ps1`
- respuestas vacías en acciones:
  - verificar `AGENT_EXECUTION_MODE`
  - usar prompts de acción explícitos
- `llama.cpp unreachable`:
  - validar ejecutable/modelo/puerto

## 7. Modo legado (opcional)

`frontend/` + `mcp_server.py` + n8n queda disponible por compatibilidad, pero no es el modo principal.
