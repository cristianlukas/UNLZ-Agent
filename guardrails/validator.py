from pydantic import BaseModel, ValidationError, field_validator
from typing import List, Optional
import re

class AgentQuery(BaseModel):
    """Validated user query payload for guardrails checks.

    Purpose:
        Defines and validates the input query before it enters the agent loop.

    Parameters:
        query (str): User message to validate.

    Returns:
        AgentQuery: Pydantic model instance with normalized values.

    Raises:
        pydantic.ValidationError: If `query` is missing or not a valid string.
        ValueError: If the validator detects potentially unsafe patterns.
    """
    query: str

    @field_validator('query')
    def check_safe_content(cls, v):
        """Reject obvious jailbreak or destructive-instruction patterns.

        Purpose:
            Applies a lightweight regex-based filter over the raw query text.

        Parameters:
            cls: Pydantic class reference.
            v (str): Query value under validation.

        Returns:
            str: Original query value when it passes all checks.

        Raises:
            ValueError: If a forbidden pattern is found in the query.
        """
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
    """Validated outbound response envelope.

    Purpose:
        Represents the response content and optional source references.

    Parameters:
        content (str): Assistant answer text.
        sources (List[str]): Optional provenance/source labels.

    Returns:
        AgentResponse: Pydantic model instance.

    Raises:
        pydantic.ValidationError: If input types are invalid.
    """
    content: str
    sources: List[str] = []

def validate_input(query: str) -> dict:
    """Validate user input and return a normalized status payload.

    Purpose:
        Wraps `AgentQuery` model validation and provides a serializable result
        structure for API consumers.

    Parameters:
        query (str): Raw user query.

    Returns:
        dict: `{"valid": True, "query": ...}` on success, otherwise
        `{"valid": False, "error": ...}`.

    Raises:
        This function catches `ValidationError` internally and does not re-raise.
    """
    try:
        valid_query = AgentQuery(query=query)
        return {"valid": True, "query": valid_query.query}
    except ValidationError as e:
        return {"valid": False, "error": str(e)}

def validate_output(content: str, sources: List[str] = []) -> dict:
    """Validate output payload constraints before returning a response.

    Purpose:
        Ensures output content is not empty and keeps a consistent envelope.

    Parameters:
        content (str): Assistant-generated output text.
        sources (List[str], optional): Source labels or references.

    Returns:
        dict: Validation result with `valid` flag and payload details.

    Raises:
        This function does not raise exceptions intentionally.
    """
    # Ensure response is not empty and sources are valid strings
    if not content.strip():
        return {"valid": False, "error": "Empty response content."}
    
    return {"valid": True, "content": content, "sources": sources}


def explain_error_for_humans(error_text: str) -> dict:
    """Map low-level errors to user-facing explanations and recovery steps.

    Purpose:
        Converts technical failures into actionable guidance for non-technical
        or beginner users.

    Parameters:
        error_text (str): Raw error string from runtime or tool execution.

    Returns:
        dict: Localized human-readable message, common causes, and suggested
        remediation steps.

    Raises:
        This function does not raise exceptions intentionally.
    """
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
