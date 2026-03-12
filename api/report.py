from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd
import io
from fastapi.responses import StreamingResponse
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import json
import requests
import urllib.parse

router = APIRouter()

class ReportRequest(BaseModel):
    instrument_name: str
    reliability: Optional[Dict[str, Any]] = None
    efa: Optional[Dict[str, Any]] = None
    ai_rel_report: Optional[str] = None
    ai_efa_report: Optional[str] = None
    full_ai_analysis: Optional[str] = None

def add_math_image(doc, latex):
    """Fetches a rendered LaTeX image and adds it to the Word document."""
    try:
        # Encode LaTeX for URL
        encoded_latex = urllib.parse.quote(rf"\large {latex}")
        url = f"https://latex.codecogs.com/png.latex?\inline \dpi{{300}} \bg_white {encoded_latex}"
        
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            img_data = io.BytesIO(response.content)
            # Add to a new centered paragraph
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run()
            run.add_picture(img_data, width=Inches(3.5)) # Standard size for "book" look
        else:
            # Fallback to text if service is down
            doc.add_paragraph(latex, style='Intense Quote')
    except Exception:
        # Extreme fallback
        doc.add_paragraph(latex, style='Intense Quote')

@router.post("/docx")
async def export_docx(req: ReportRequest):
    try:
        doc = Document()
        
        # Estilo Global
        style = doc.styles['Normal']
        font = style.font
        font.name = 'Georgia'
        font.size = Pt(11)
        
        # Portada / Título
        title_section = doc.add_heading(f"Reporte Psicométrico Profesional", 0)
        title_section.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        inst_name = doc.add_paragraph(req.instrument_name or "Instrumento de Investigación")
        inst_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
        inst_name.runs[0].bold = True
        inst_name.runs[0].font.size = Pt(16)
        
        doc.add_page_break()

        # Índice Mental / Introducción
        doc.add_heading("I. Introducción y Resumen Ejecutivo", level=1)
        if req.full_ai_analysis:
            doc.add_paragraph(req.full_ai_analysis)
        else:
            doc.add_paragraph("Este informe presenta los resultados de los análisis de consistencia interna y validez de constructo realizados sobre el instrumento.")

        # 1. Confiabilidad
        doc.add_heading("II. Análisis de Fiabilidad (Consistencia Interna)", level=1)
        doc.add_paragraph(
            "La fiabilidad es la precisión con la que el instrumento mide el constructo. "
            "Se han calculado el Alfa de Cronbach y el Omega de McDonald para evaluar la relación entre los ítems."
        )
        
        if req.reliability:
            # Alfa de Cronbach Desarrollo
            doc.add_heading("2.1. Coeficiente Alfa de Cronbach", level=2)
            res_c = req.reliability.get("cronbach", {})
            doc.add_paragraph(f"El valor obtenido es α = {res_c.get('alpha', 'N/A')}.")
            
            doc.add_heading("2.1.1. Insumos para el cálculo (Varianzas)", level=3)
            doc.add_paragraph(
                "Para obtener el Alfa de Cronbach, primero calculamos la varianza individual de cada uno de los ítems "
                "y la varianza total de la suma de los puntajes."
            )
            
            # Table for Item Variances
            stats = res_c.get("item_stats", [])
            if stats:
                table_v = doc.add_table(rows=1, cols=3)
                table_v.style = 'Table Grid'
                hdr = table_v.rows[0].cells
                hdr[0].text = "Ítem"
                hdr[1].text = "Media"
                hdr[2].text = "Varianza (σ²)"
                
                for s in stats:
                    row = table_v.add_row().cells
                    row[0].text = str(s.get("item"))
                    row[1].text = f"{s.get('mean', 0):.3f}"
                    # Individual variances are not in item_stats, let's assume we can get them or use std_dev^2
                    row[2].text = f"{s.get('std_dev', 0)**2:.3f}"

            doc.add_heading("Desarrollo Matemático Detallado:", level=3)
            doc.add_paragraph("La fórmula de Cronbach se basa en la relación entre la suma de varianzas individuales y la varianza total:")
            add_math_image(doc, res_c.get("equation", r"\alpha = \frac{k}{k-1} ..."))
            
            doc.add_paragraph(
                f"Donde k = {res_c.get('n_items')} ítems. "
                f"La suma de las varianzas individuales (∑σᵢ²) es {res_c.get('sum_item_variances')} "
                f"y la varianza total observada (σₜ²) es {res_c.get('total_variance')}."
            )
            
            doc.add_paragraph("Sustitución técnica:")
            add_math_image(doc, res_c.get("equation_values", ""))
            
            # Omega de McDonald
            doc.add_heading("2.2. Coeficiente Omega de McDonald", level=2)
            res_o = req.reliability.get("mcdonald_omega", {})
            if res_o and not res_o.get("error"):
                doc.add_paragraph(f"El valor de Omega es ω = {res_o.get('omega', 'N/A')}.")
                doc.add_paragraph(
                    "El coeficiente Omega es más robusto ya que utiliza las cargas factoriales (λ) de un Análisis Factorial "
                    "de un solo factor para ponderar la importancia de cada ítem."
                )
                
                doc.add_heading("2.2.1. Pesos y Unicidades (Cargas Factoriales)", level=3)
                doc.add_paragraph(
                    "A continuación se presentan los valores de carga (λ), que representan la relación del ítem con el factor, "
                    "y la unicidad (u²), que representa el error de medición o varianza no compartida."
                )
                
                loadings = res_o.get("loadings", [])
                uniquenesses = res_o.get("uniquenesses", [])
                
                if loadings and uniquenesses:
                    table_o = doc.add_table(rows=1, cols=3)
                    table_o.style = 'Table Grid'
                    hdr_o = table_o.rows[0].cells
                    hdr_o[0].text = "Ítem"
                    hdr_o[1].text = "Carga (λ)"
                    hdr_o[2].text = "Unicidad (u²)"
                    
                    # We need the item names, which we can get from item_stats if available
                    items = [s.get("item") for s in res_c.get("item_stats", [])]
                    for i, (l, u) in enumerate(zip(loadings, uniquenesses)):
                        row = table_o.add_row().cells
                        row[0].text = str(items[i]) if i < len(items) else f"Ítem {i+1}"
                        row[1].text = f"{l:.3f}"
                        row[2].text = f"{u:.3f}"

                add_math_image(doc, res_o.get("equation", ""))
                doc.add_paragraph(
                    f"Donde la suma de cargas al cuadrado (∑λ)² es {res_o.get('sum_loadings_sq')} "
                    f"y la suma de unicidades (∑u²) es {res_o.get('sum_uniqueness')}."
                )
                doc.add_paragraph("Sustitución técnica:")
                add_math_image(doc, res_o.get("equation_values", ""))

            # AI Interpretation
            if req.ai_rel_report:
                doc.add_heading("Interpretación Técnica Sugerida:", level=3)
                doc.add_paragraph(req.ai_rel_report)

        # 2. Análisis Factorial
        doc.add_heading("III. Análisis Factorial Exploratorio (Validez de Constructo)", level=1)
        doc.add_paragraph(
            "El Análisis Factorial permite identificar las dimensiones subyacentes del test, "
            "verificando si los ítems se agrupan de acuerdo con la teoría propuesta."
        )
        
        if req.efa:
            doc.add_heading("3.1. Pruebas de Calidad Muestral", level=2)
            ade = req.efa.get("adequacy", {})
            kmo = ade.get("kmo", {})
            bart = ade.get("bartlett", {})
            
            # KMO Equation
            doc.add_heading("Índice KMO:", level=3)
            doc.add_paragraph(
                "El índice KMO (Kaiser-Meyer-Olkin) compara las correlaciones observadas con las correlaciones parciales. "
                "Valores cercanos a 1 indican que el análisis factorial es muy adecuado."
            )
            add_math_image(doc, kmo.get("equation", ""))
            
            if kmo.get("equation_values"):
                doc.add_paragraph("Sustitución técnica:")
                add_math_image(doc, kmo.get("equation_values"))
            
            # Bartlett Equation
            doc.add_heading("Prueba de Bartlett:", level=3)
            doc.add_paragraph(
                "Esta prueba evalúa la hipótesis nula de que la matriz de correlaciones es una matriz identidad "
                "(es decir, que no hay relación entre los ítems)."
            )
            add_math_image(doc, bart.get("equation", ""))
            
            if bart.get("equation_values"):
                doc.add_paragraph("Desarrollo Matemático:")
                add_math_image(doc, bart.get("equation_values"))
            
            table_ade = doc.add_table(rows=3, cols=2)
            table_ade.style = 'Table Grid'
            hdr_a = table_ade.rows[0].cells
            hdr_a[0].text = "Estadístico"
            hdr_a[1].text = "Resultado"
            
            table_ade.cell(1,0).text = "Kaiser-Meyer-Olkin (KMO)"
            table_ade.cell(1,1).text = f"{kmo.get('value')} ({kmo.get('interpretation')})"
            
            table_ade.cell(2,0).text = "Bartlett (p-valor)"
            table_ade.cell(2,1).text = f"{bart.get('p_value')} ({'Significativo' if bart.get('significant') else 'No Significativo'})"

            # Explained Variance Section
            doc.add_heading("3.2. Varianza Explicada (Autovalores)", level=2)
            doc.add_paragraph(
                "Los autovalores (eigenvalues) indican la cantidad de varianza total que explica cada factor. "
                "Siguiendo el criterio de Kaiser, se retienen factores con autovalores superiores a 1."
            )
            
            extraction = req.efa.get("extraction", {})
            eigenvalues = extraction.get("eigenvalues", [])
            if eigenvalues:
                table_e = doc.add_table(rows=1, cols=3)
                table_e.style = 'Table Grid'
                hdr_e = table_e.rows[0].cells
                hdr_e[0].text = "Factor"
                hdr_e[1].text = "Autovalor"
                hdr_e[2].text = "% Varianza (Aprox.)"
                
                total_ev = sum(eigenvalues)
                for i, ev in enumerate(eigenvalues):
                    if i >= 10: break # Don't list too many
                    row = table_e.add_row().cells
                    row[0].text = f"Factor {i+1}"
                    row[1].text = f"{ev:.3f}"
                    row[2].text = f"{(ev/total_ev*100):.2f}%"

            # Matriz de Cargas
            loadings = req.efa.get("loadings", [])
            if loadings:
                doc.add_heading("3.3. Matriz de Cargas Factoriales", level=2)
                doc.add_paragraph("Esta tabla muestra cuánto 'pesa' cada ítem en los factores identificados (Cargas > 0.40 se consideran significativas):")
                
                cols = list(loadings[0].keys())
                table_efa = doc.add_table(rows=1, cols=len(cols))
                table_efa.style = 'Table Grid'
                hdr = table_efa.rows[0].cells
                for i, c in enumerate(cols):
                    hdr[i].text = c
                
                for row_data in loadings:
                    cells = table_efa.add_row().cells
                    for i, c in enumerate(cols):
                        val = row_data[c]
                        cells[i].text = f"{val:.3f}" if isinstance(val, (float)) else str(val)

            # AI Interpretation EFA
            if req.ai_efa_report:
                doc.add_heading("Conclusiones de la Estructura Factorial:", level=3)
                doc.add_paragraph(req.ai_efa_report)

        # Final
        doc.add_heading("IV. Firma del Sistema", level=1)
        doc.add_paragraph("Este documento tiene validez académica y científica para ser utilizado en procesos de validación de instrumentos.")

        # Save to memory
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        safe_name = (req.instrument_name or "Reporte").replace(" ", "_")
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=Reporte_{safe_name}.docx"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/xlsx")
async def export_xlsx(req: ReportRequest):
    try:
        output = io.BytesIO()
        # Use pandas with xlsxwriter
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Summary
            if req.reliability:
                rel_data = {
                    "Métrica": ["Alfa de Cronbach", "Omega de McDonald"],
                    "Valor": [
                        req.reliability.get("cronbach", {}).get("alpha"),
                        req.reliability.get("mcdonald_omega", {}).get("omega")
                    ],
                    "N Ítems": [
                        req.reliability.get("cronbach", {}).get("n_items"),
                        "N/A"
                    ]
                }
                pd.DataFrame(rel_data).to_excel(writer, sheet_name="Confiabilidad", index=False)
            
            # Loadings
            if req.efa and req.efa.get("loadings"):
                pd.DataFrame(req.efa["loadings"]).to_excel(writer, sheet_name="Matriz de Cargas", index=False)
            
            # Eigenvalues (if available)
            if req.efa and req.efa.get("extraction", {}).get("eigenvalues"):
                eig_data = pd.DataFrame({
                    "Componente": range(1, len(req.efa["extraction"]["eigenvalues"]) + 1),
                    "Autovalor (Eigenvalue)": req.efa["extraction"]["eigenvalues"]
                })
                eig_data.to_excel(writer, sheet_name="Autovalores", index=False)
                
        output.seek(0)
        safe_name = (req.instrument_name or "Datos").replace(" ", "_")
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Matriz_{safe_name}.xlsx"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
