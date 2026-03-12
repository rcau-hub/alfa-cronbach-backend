from fastapi import APIRouter, UploadFile, File, HTTPException
import pandas as pd
import numpy as np
import io

router = APIRouter()

@router.post("/")
async def upload_dataset(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No se seleccionó ningún archivo")

    try:
        content = await file.read()
        
        # Determine file type
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content))
        elif file.filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(io.BytesIO(content))
        elif file.filename.endswith('.sav'):
            import pyreadstat
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.sav') as tmp:
                tmp.write(content)
                tmp_path = tmp.name
                
            df, meta = pyreadstat.read_sav(tmp_path)
            os.remove(tmp_path)
            
        elif file.filename.endswith('.pdf'):
            import PyPDF2
            import requests
            import os
            
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            text = ""
            for i, page in enumerate(reader.pages):
                if i > 10: break # Limitar a 10 páginas máximo por seguridad
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"

            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key or api_key == "your_api_key_here":
                raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY no configurada para procesar PDFs mediante IA.")
                
            system_prompt = (
                "Eres un extractor de datos de tablas. El usuario te proporcionará texto sucio extraído de un PDF. "
                "Tu tarea es encontrar la tabla principal (dataset de estudio con filas y columnas). "
                "Debes responder ESTRICTAMENTE y ÚNICAMENTE con los datos en formato CSV puro, sin bloque de código Markdown (```csv), sin texto explicativo. "
                "La primera fila deben ser los nombres de las variables (ej. V1, V2, Item1). Las demás filas son datos separados por comas."
            )
            # Limit to avoiding huge payloads over context bounds for basic models
            user_prompt = f"Convierte el siguiente texto a CSV puro:\n\n{text[:20000]}"
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": os.getenv("FRONTEND_URL", "http://localhost:3000"),
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "openai/gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1
            }
            
            ai_resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
            if not ai_resp.ok:
                raise HTTPException(status_code=500, detail=f"Error en OpenRouter ({ai_resp.status_code}): {ai_resp.text}")
                
            ai_data = ai_resp.json()
            csv_content = ai_data["choices"][0]["message"]["content"].strip()
            
            if csv_content.startswith("```"):
                lines = csv_content.splitlines()
                # Skip first line and last line if they are markdown fences
                if lines[0].startswith("```"): lines = lines[1:]
                if lines[-1].startswith("```"): lines = lines[:-1]
                csv_content = "\n".join(lines)
                
            try:
                df = pd.read_csv(io.StringIO(csv_content))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"No se pudo parsear el CSV devuelto por la IA. Respuesta cruda: {csv_content[:200]}...")

        else:
             raise HTTPException(status_code=400, detail="Formato de archivo no soportado. Usa .csv, .xlsx, .sav o .pdf.")

        # Basic data cleaning overview
        summary = {
            "filename": file.filename,
            "rows": len(df),
            "columns": len(df.columns),
            "variables": list(df.columns),
            "missing_values": int(df.isnull().sum().sum())
        }
        
        # In a real app we'd save this DF to database/redis/session.
        # For this prototype we will assume the frontend sends the dataset or a token.
        # To keep it simple, we'll return the head of the data in records format to let the user select vars.
        
        data_preview = df.head(10).replace({np.nan: None}).to_dict(orient="records")
        data_full = df.replace({np.nan: None}).to_dict(orient="records")

        return {
            "message": "Archivo cargado correctamente",
            "summary": summary,
            "preview": data_preview,
            "data": data_full
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando el archivo: {str(e)}")
