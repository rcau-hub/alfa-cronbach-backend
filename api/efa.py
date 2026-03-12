from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from factor_analyzer import FactorAnalyzer
from factor_analyzer.factor_analyzer import calculate_kmo, calculate_bartlett_sphericity

router = APIRouter()

class EFARequest(BaseModel):
    data: List[Dict[str, Any]]
    variables: List[str]
    method: str = "principal" # 'principal' or 'ml'
    rotation: Optional[str] = "varimax" # 'varimax', 'promax', 'oblimin', None
    n_factors: Optional[int] = None # If None, determine by Kaiser criterion or scree plot

@router.post("/analysis")
async def analyze_efa(req: EFARequest):
    try:
        df = pd.DataFrame(req.data)[req.variables].apply(pd.to_numeric, errors='coerce').dropna()
        
        if len(df.columns) < 3:
             raise ValueError("El Análisis Factorial Exploratorio requiere al menos 3 variables.")
             

        # Add numerical stability to prevent "Singular Matrix" crashes
        # by breaking exact collinearity with an imperceptible micro-variance
        df = df.astype(float)
        np.random.seed(42)
        df = df + np.random.normal(0, 1e-8, df.shape)

        # Helper to clean NaN values for JS compatibility
        def sanitize_val(val):
            if isinstance(val, (float, np.float64, np.float32)) and (np.isnan(val) or np.isinf(val)):
                return 0.0
            try:
                return float(val)
            except:
                return val

        # Adequacy Tests
        # KMO
        try:
            kmo_all, kmo_model = calculate_kmo(df)
            kmo_val = sanitize_val(kmo_model)
            kmo = {
                "value": round(kmo_val, 3),
                "interpretation": "Adecuado" if kmo_val >= 0.6 else "No Adecuado",
                "equation": r"KMO = \frac{\sum \sum_{i \neq j} r_{ij}^2}{\sum \sum_{i \neq j} r_{ij}^2 + \sum \sum_{i \neq j} p_{ij}^2}",
                "equation_values": rf"KMO = {round(kmo_val, 3)}"
            }
        except Exception as e:
            kmo = {
                "value": 0,
                "interpretation": "Error (Matriz Singular)",
                "equation": r"KMO = \frac{\sum \sum_{i \neq j} r_{ij}^2}{\sum \sum_{i \neq j} r_{ij}^2 + \sum \sum_{i \neq j} p_{ij}^2}",
                "equation_values": "Error matemático: Datos redundantes o N < Variables"
            }
        
        # Bartlett
        try:
            chi_square_value, p_value = calculate_bartlett_sphericity(df)
            chi_val = sanitize_val(chi_square_value)
            p_val_clean = sanitize_val(p_value)
            bartlett = {
                "chi_square": round(chi_val, 3),
                "p_value": round(p_val_clean, 4),
                "significant": bool(p_val_clean < 0.05),
                "equation": r"\chi^2 = -\left( (n-1) - \frac{2p+5}{6} \right) \ln |R|",
                "equation_values": rf"\chi^2 = {round(chi_val, 3)}, \quad p \approx {round(p_val_clean, 4)}"
            }
        except Exception as e:
            bartlett = {
                "chi_square": 0,
                "p_value": 1,
                "significant": False,
                "equation": r"\chi^2 = -\left( (n-1) - \frac{2p+5}{6} \right) \ln |R|",
                "equation_values": "Error matemático: Datos redundantes o N < Variables"
            }
        
        # Determine number of factors if not specified
        try:
            fa_initial = FactorAnalyzer(rotation=None)
            fa_initial.fit(df)
            eigenvalues, _ = fa_initial.get_eigenvalues()
        except Exception as e:
             # If initial eigenvalues fail, use identity covariance as fallback for eigenvalues
             eigenvalues = np.ones(len(df.columns))
        
        if req.n_factors is None:
            # Kaiser Criterion (Eigenvalues > 1)
            n_factors = sum(eigenvalues > 1)
            if n_factors == 0:
                n_factors = 1 # Force at least 1 factor
        else:
            n_factors = req.n_factors
            
        # Ensure n_factors is not too large for the data
        n_factors = min(int(n_factors), len(df.columns) - 1)
        if n_factors < 1: n_factors = 1

        # Run final EFA
        try:
            analyzer = FactorAnalyzer(n_factors=n_factors, method=req.method, rotation=req.rotation)
            analyzer.fit(df)
        except Exception as e:
            # Final fallback: Principal Component style loadings or error report
            raise ValueError(f"No se pudo completar el análisis factorial con estos datos: {str(e)}. Intenta reducir el número de variables o cambiar el método de extracción.")

        
        loadings = analyzer.loadings_
        communalities = analyzer.get_communalities()
        
        # Format Loadings Table
        factors_labels = [f"Factor {i+1}" for i in range(n_factors)]
        loadings_df = pd.DataFrame(loadings, index=df.columns, columns=factors_labels)
        
        # Identify cross-loadings or low discrimination (optional warning logic)
        warnings = []
        for i, row in loadings_df.iterrows():
            significant_loadings = sum(abs(row) >= 0.40)
            if significant_loadings > 1:
                warnings.append(f"El ítem '{i}' presenta cargas cruzadas significativas (≥ 0.40).")
            elif significant_loadings == 0:
                warnings.append(f"El ítem '{i}' no carga significativamente (≥ 0.40) en ningún factor.")
                

        # Data for Scree Plot
        scree_plot_data = {
            "factors": list(range(1, len(eigenvalues) + 1)),
            "eigenvalues": [float(round(sanitize_val(e), 3)) for e in eigenvalues]
        }

        # Clean loadings records
        loadings_records = loadings_df.reset_index().rename(columns={"index": "Item"}).to_dict(orient="records")
        for record in loadings_records:
            for k, v in record.items():
                record[k] = sanitize_val(v)

        return {
            "adequacy": {
                "kmo": kmo,
                "bartlett": bartlett
            },
            "extraction": {
                "n_factors": int(n_factors),
                "method": req.method,
                "rotation": req.rotation,
                "eigenvalues": [float(round(sanitize_val(e), 3)) for e in eigenvalues]
            },
            "loadings": loadings_records,
            "communalities": {item: float(round(sanitize_val(com), 3)) for item, com in zip(df.columns, communalities)},
            "warnings": warnings,
            "scree_plot_data": scree_plot_data
        }
        
    except ValueError as e:
        if "singular" in str(e).lower():
            raise HTTPException(
                status_code=400, 
                detail="Error en la matriz: " + str(e) + ". Esto ocurre porque las variables seleccionadas están perfectamente correlacionadas o son redundantes."
            )
        raise HTTPException(status_code=400, detail=str(e))
    except np.linalg.LinAlgError as e:
        if "Singular matrix" in str(e):
            raise HTTPException(
                status_code=400, 
                detail="Error determinando la cantidad de factores: Singular matrix. Esto ocurre porque algunas de las variables seleccionadas están perfectamente correlacionadas (redundantes) o porque hay una variable con varianza cercana a cero. Por favor, revisa tus datos o elimina variables redundantes."
            )
        raise HTTPException(status_code=500, detail=f"Error de Álgebra Lineal: {str(e)}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en el EFA: {str(e)}")
