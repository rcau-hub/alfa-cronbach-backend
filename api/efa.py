from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
import traceback
from factor_analyzer import FactorAnalyzer
from factor_analyzer.factor_analyzer import calculate_kmo, calculate_bartlett_sphericity

router = APIRouter()

class EFARequest(BaseModel):
    data: List[Dict[str, Any]]
    variables: List[str]
    method: str = "principal" # 'principal' or 'ml'
    rotation: Optional[str] = "varimax" 
    n_factors: Optional[int] = None 

def safe_float(val):
    try:
        fval = float(val)
        if np.isfinite(fval):
            return fval
        return 0.0
    except:
        return 0.0

@router.post("/analysis")
async def analyze_efa(req: EFARequest):
    try:
        df = pd.DataFrame(req.data)[req.variables].apply(pd.to_numeric, errors='coerce').dropna()
        
        if len(df) < 5:
             raise ValueError("El Análisis Factorial requiere al menos 5 casos válidos (filas) para ser estadísticamente posible.")
             
        # KMO
        try:
            kmo_all, kmo_model = calculate_kmo(df)
            kmo_val = safe_float(kmo_model)
            kmo = {
                "value": kmo_val,
                "interpretation": "Adecuado" if kmo_val >= 0.6 else "No Adecuado",
                "equation": r"KMO = \frac{\sum \sum_{i \neq j} r_{ij}^2}{\sum \sum_{i \neq j} r_{ij}^2 + \sum \sum_{i \neq j} p_{ij}^2}",
                "equation_values": r"KMO \approx \frac{\sum r_{ij}^2}{\sum r_{ij}^2 + \sum p_{ij}^2} = " + str(round(kmo_val, 3))
            }
        except Exception as e:
            kmo = {"value": 0.0, "interpretation": "Error", "equation": "", "equation_values": str(e)}
            
        # Bartlett
        try:
            chi_val, p_val = calculate_bartlett_sphericity(df)
            n_o = len(df)
            p_i = len(df.columns)
            
            # Intermediate values
            m_val = (n_o - 1) - (2 * p_i + 5) / 6.0
            l_val = -float(chi_val) / m_val if (m_val != 0 and np.isfinite(chi_val)) else 0.0
            
            m_s = str(round(safe_float(m_val), 3))
            l_s = str(round(safe_float(l_val), 4))
            c_s = str(round(safe_float(chi_val), 3))
            
            bartlett_dev = (
                r"\begin{aligned} "
                r"& \chi^2 = -\left( (" + str(n_o) + r"-1) - \frac{2(" + str(p_i) + r")+5}{6} \right) \ln |R| \\ "
                r"& \chi^2 = -(" + m_s + r") \times (" + l_s + r") \\ "
                r"& \chi^2 = " + c_s + r" "
                r"\end{aligned}"
            )

            bartlett = {
                "chi_square": safe_float(chi_val),
                "p_value": safe_float(p_val),
                "significant": bool(safe_float(p_val) < 0.05),
                "equation": r"\chi^2 = -\left( (n-1) - \frac{2p+5}{6} \right) \ln |R|",
                "equation_values": bartlett_dev
            }
        except Exception as e:
            bartlett = {"chi_square": 0.0, "p_value": 1.0, "significant": False, "equation": "", "equation_values": str(e)}
            
        # Determine number of factors
        try:
            fa_initial = FactorAnalyzer(rotation=None)
            fa_initial.fit(df)
            eigenvalues, _ = fa_initial.get_eigenvalues()
            
            if req.n_factors is None:
                n_factors = int(np.sum(eigenvalues > 1))
                if n_factors == 0: n_factors = 1
            else:
                n_factors = int(req.n_factors)
        except Exception as e:
            raise ValueError(f"Error determinando la cantidad de factores: {str(e)}")
            
        # Run final EFA
        try:
            analyzer = FactorAnalyzer(n_factors=n_factors, method=req.method, rotation=req.rotation)
            analyzer.fit(df)
            
            loadings = analyzer.loadings_
            communalities = analyzer.get_communalities()
        except Exception as e:
            raise ValueError(f"Error en la extracción de factores: {str(e)}. Intenta reducir el número de factores.")
            
        # Format Loadings Table
        factors_labels = [f"Factor {i+1}" for i in range(n_factors)]
        loadings_df = pd.DataFrame(loadings, index=df.columns, columns=factors_labels)
        
        # Warnings
        warnings = []
        for item_name, row in loadings_df.iterrows():
            significant_count = int(np.sum(np.abs(row.values) >= 0.40))
            if significant_count > 1:
                warnings.append(f"El ítem '{item_name}' presenta cargas cruzadas (≥ 0.40).")
            elif significant_count == 0:
                warnings.append(f"El ítem '{item_name}' no carga lo suficiente (≥ 0.40) en ningún factor.")
                
        # Data for Scree Plot
        scree_plot_data = {
            "factors": list(range(1, len(eigenvalues) + 1)),
            "eigenvalues": [safe_float(e) for e in eigenvalues]
        }

        return {
            "adequacy": { "kmo": kmo, "bartlett": bartlett },
            "extraction": {
                "n_factors": n_factors,
                "method": req.method,
                "rotation": req.rotation,
                "eigenvalues": [safe_float(e) for e in eigenvalues]
            },
            "loadings": loadings_df.reset_index().rename(columns={"index": "Item"}).to_dict(orient="records"),
            "communalities": {item: safe_float(com) for item, com in zip(df.columns, communalities)},
            "warnings": warnings,
            "scree_plot_data": scree_plot_data
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error inesperado en EFA: {str(e)}")
