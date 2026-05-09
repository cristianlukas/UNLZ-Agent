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
