from pydantic import BaseModel, ValidationError, field_validator
from typing import List, Optional
import re

class AgentQuery(BaseModel):
    query: str

    @field_validator('query')
    def check_safe_content(cls, v):
        # Basic injection/jailbreak detection
        forbidden_patterns = [
            r"ignore previous instructions",
            r"system prompt",
            r"delete database",
            r"drop table"
        ]
        for pattern in forbidden_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Unsafe content detected in query.")
        return v

class AgentResponse(BaseModel):
    content: str
    sources: List[str] = []

def validate_input(query: str) -> dict:
    try:
        valid_query = AgentQuery(query=query)
        return {"valid": True, "query": valid_query.query}
    except ValidationError as e:
        return {"valid": False, "error": str(e)}

def validate_output(content: str, sources: List[str] = []) -> dict:
    # Ensure response is not empty and sources are valid strings
    if not content.strip():
        return {"valid": False, "error": "Empty response content."}
    
    return {"valid": True, "content": content, "sources": sources}


def explain_error_for_humans(error_text: str) -> dict:
    raw = str(error_text or "").strip()
    low = raw.lower()
    if "timeout" in low:
        return {
            "human_message": "La tarea tardó más de lo esperado y se interrumpió.",
            "common_causes": [
                "Modelo pesado o en carga inicial",
                "Comando bloqueado esperando salida",
                "Falta de recursos (RAM/VRAM)",
            ],
            "fix_steps": [
                "Reintentá la misma tarea con un pedido más corto",
                "Esperá a que termine la carga del modelo y probá de nuevo",
                "Si persiste, usá modo simple o un modelo más liviano",
            ],
        }
    if "no instalado" in low or "not found" in low or "no encontrado" in low:
        return {
            "human_message": "Falta una herramienta necesaria para completar la tarea.",
            "common_causes": [
                "Dependencia no instalada",
                "Ruta del ejecutable mal configurada",
            ],
            "fix_steps": [
                "Abrí Onboarding y ejecutá 'Dejar todo listo'",
                "Verificá configuración de binarios en Ajustes",
                "Reintentá la tarea",
            ],
        }
    return {
        "human_message": "Hubo un error al ejecutar la tarea.",
        "common_causes": [
            "Entrada no válida",
            "Estado interno inconsistente",
            "Dependencia temporalmente no disponible",
        ],
        "fix_steps": [
            "Probá nuevamente",
            "Si se repite, ejecutá Onboarding para diagnóstico",
            "Compartí el mensaje técnico para revisión",
        ],
    }
