from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import requests
from typing import Optional

router = APIRouter()

class InterpretationRequest(BaseModel):
    analysis_type: str # "reliability" or "efa"
    context_data: dict # The JSON output from previous analysis
    instrument_name: str = ""
    user_interpretation: Optional[str] = None # What the student wrote
    is_socratic: bool = False # If true, act as a guide/mentor

@router.post("/prompt")
async def generate_interpretation(req: InterpretationRequest):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY no configurada.")
        
    if req.is_socratic and req.user_interpretation:
        # TUTOR SOCRATICO MODE
        system_prompt = (
            "Eres un Profesor Mentor de Psicometría en una sesión de tutoría 1-a-1. "
            "Tu objetivo es usar el método SOCRÁTICO (Andamiaje/Scaffolding). "
            "REGLAS ESTRICTAS:\n"
            "1. NO des la respuesta correcta de inmediato.\n"
            "2. Evalúa lo que el estudiante escribió como interpretación.\n"
            "3. Si es incompleto o erróneo, felicita el esfuerzo pero lanza una PREGUNTA o PISTA que lo haga reflexionar. "
            "Ejemplo: 'Vas bien, pero ¿qué pasaría con el error de medición si ese Alfa fuera 0.60 en lugar del 0.85 que obtuviste?'\n"
            "4. Sé breve, empático y motivador. Usa metáforas de la vida real.\n"
            "5. Si la respuesta es perfecta, felicítalo efusivamente y confirma que su razonamiento es digno de una publicación científica."
        )
        user_prompt = (
            f"Resultados técnicos: {req.context_data}\n"
            f"Lo que el estudiante interpretó: '{req.user_interpretation}'\n\n"
            "Responde como su mentor socrático. Guíalo sin regalarle la solución."
        )
    elif req.analysis_type == "complete_report":
        # FORMAL REPORT SUMMARY MODE
        system_prompt = (
            "Eres un experto en Psicometría y Metodología de la Investigación. "
            "Tu tarea es redactar el RESUMEN EJECUTIVO e INTRODUCCIÓN de un reporte técnico formal. "
            "Estilo: Académico, sobrio, preciso (estilo APA). "
            "1. Comienza con una visión general del instrumento y su propósito.\n"
            "2. Resume los hallazgos de fiabilidad (Alfa/Omega).\n"
            "3. Resume la validez de constructo (EFA/KMO/Bartlett).\n"
            "4. Concluye si el instrumento es apto para su aplicación masiva.\n"
            "Evita el lenguaje informal o socrático. Sé profesional."
        )
        user_prompt = f"Redacta el resumen formal para '{req.instrument_name}' basado en estos datos combinados:\n\n{req.context_data}"
    else:
        # NORMAL MODE (BUT PEDAGOGICAL)
        system_prompt = (
            "Eres un profesor experto en estadística y psicometría, con un estilo interactivo y didáctico. "
            "Háblale de 'tú' al estudiante. Sé breve y estructurado.\n"
            "1. Resumen Ejecutivo (2-3 líneas).\n"
            "2. Detalles Matemáticos en Fácil (Exponiendo K, P, Autovalores, etc.).\n"
            "NO uses negritas dobles (**) o encabezados complejo (#). Usa guiones (-) y texto limpio."
        )
        user_prompt = f"Interpreta estos resultados de {req.analysis_type} para '{req.instrument_name}':\n\n{req.context_data}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.5
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return {"interpretation": result["choices"][0]["message"]["content"]}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))
