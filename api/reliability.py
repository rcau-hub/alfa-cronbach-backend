from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import pandas as pd
import numpy as np
import traceback
from factor_analyzer import FactorAnalyzer

router = APIRouter()

class ReliabilityRequest(BaseModel):
    data: List[Dict[str, Any]] # Array of records representing the dataframe
    variables: List[str] # Columns to analyze

def safe_float(val):
    try:
        fval = float(val)
        if np.isfinite(fval):
            return fval
        return 0.0
    except:
        return 0.0

def calculate_cronbach_alpha(df: pd.DataFrame):
     # Convert to numeric, errors to NaN, then drop NaNs
     df = df.apply(pd.to_numeric, errors='coerce').dropna()
     
     if len(df.columns) < 2:
          raise ValueError("El Alfa de Cronbach requiere al menos 2 variables.")
     
     if len(df) < 2:
          raise ValueError("No hay suficientes casos válidos después de eliminar valores faltantes.")
          
     n_items = float(len(df.columns))
     
     # Calculate covariance matrix
     cov_matrix = df.cov()
     
     # Calculate item variances and total variance
     item_variances = np.diag(cov_matrix)
     sum_item_variances = float(np.sum(item_variances))
     total_variance = float(np.sum(cov_matrix.values))
     
     if total_variance == 0:
          alpha = 0.0
          val1, val2, val3 = 0, 0, 0
     else:
          alpha = float((n_items / (n_items - 1)) * (1 - (sum_item_variances / total_variance)))
          val1 = round(n_items / (n_items - 1), 3)
          val2 = round(sum_item_variances / total_variance, 3)
          val3 = round(1 - val2, 3)
     
     # Explicit types for formatting
     k_items = int(n_items)
     chi_str = str(round(safe_float(alpha), 3))
     sum_v_str = str(round(safe_float(sum_item_variances), 3))
     tot_v_str = str(round(safe_float(total_variance), 3))

     # Multi-step development string - Using concatenation for LaTeX safely
     development = (
         r"\begin{aligned} "
         r"& \alpha = \frac{" + str(k_items) + r"}{" + str(k_items) + r"-1} \left( 1 - \frac{" + sum_v_str + r"}{" + tot_v_str + r"} \right) \\ "
         r"& \alpha = " + str(val1) + r" \times (1 - " + str(val2) + r") \\ "
         r"& \alpha = " + str(val1) + r" \times " + str(val3) + r" \\ "
         r"& \alpha = " + chi_str + r" "
         r"\end{aligned}"
     )

     # Calculate item-total correlations and alpha if item deleted
     item_stats = []
     mean_scores = df.mean().to_dict()
     std_scores = df.std().to_dict()
     
     for item in df.columns:
          # Item-total correlation corrected (correlation between item and sum of other items)
          other_items_sum = df.drop(columns=[item]).sum(axis=1)
          item_total_corr = float(df[item].corr(other_items_sum))
          
          # Alpha if item deleted
          df_deleted = df.drop(columns=[item])
          cov_matrix_del = df_deleted.cov()
          item_vars_del = np.sum(np.diag(cov_matrix_del))
          total_var_del = np.sum(cov_matrix_del.values)
          
          n_items_del = n_items - 1
          if total_var_del == 0 or n_items_del <= 1:
             alpha_del = 0.0
          else:
             alpha_del = float((n_items_del / (n_items_del - 1)) * (1 - (item_vars_del / total_var_del)))
             
          item_stats.append({
              "item": item,
              "mean": safe_float(mean_scores[item]),
              "std_dev": safe_float(std_scores[item]),
              "item_total_corr": safe_float(item_total_corr),
              "alpha_if_deleted": safe_float(alpha_del)
          })
          
     equation = r"\alpha = \frac{k}{k-1} \left( 1 - \frac{\sum_{i=1}^{k} \sigma_i^2}{\sigma_T^2} \right)"
     equation_values = r"\alpha = \frac{" + str(k_items) + r"}{" + str(k_items) + r"-1} \left( 1 - \frac{" + sum_v_str + r"}{" + tot_v_str + r"} \right) = " + chi_str

     return {
         "alpha": round(safe_float(alpha), 3),
         "n_items": k_items,
         "sum_item_variances": round(safe_float(sum_item_variances), 3),
         "total_variance": round(safe_float(total_variance), 3),
         "item_variances": [round(safe_float(v), 3) for v in item_variances],
         "equation": equation,
         "equation_values": equation_values,
         "development": development,
         "item_stats": item_stats
     }

def calculate_mcdonalds_omega(df: pd.DataFrame):
    df = df.apply(pd.to_numeric, errors='coerce').dropna()
    
    if len(df.columns) < 3:
        raise ValueError("Omega requiere al menos 3 variables.")
    
    # 1 factor EFA (minres is robust for Omega)
    fa = FactorAnalyzer(n_factors=1, method='minres', rotation=None)
    fa.fit(df)
    
    loadings = fa.loadings_.flatten()
    uniqueness = 1 - fa.get_communalities()
    
    sum_loadings = np.sum(loadings)
    sum_loadings_sq = sum_loadings ** 2
    sum_uniqueness = np.sum(uniqueness)
    
    denominator = sum_loadings_sq + sum_uniqueness
    omega = sum_loadings_sq / denominator if denominator != 0 else 0.0
    
    # Mathematical development strings
    sum_l_str = str(round(safe_float(sum_loadings), 3))
    sum_l_sq_str = str(round(safe_float(sum_loadings_sq), 3))
    sum_u_str = str(round(safe_float(sum_uniqueness), 3))
    omega_str = str(round(safe_float(omega), 3))

    development = (
        r"\begin{aligned} "
        r"& \omega = \frac{(\sum \lambda_i)^2}{(\sum \lambda_i)^2 + \sum \psi_i} \\ "
        r"& \omega = \frac{(" + sum_l_str + r")^2}{(" + sum_l_str + r")^2 + " + sum_u_str + r"} \\ "
        r"& \omega = \frac{" + sum_l_sq_str + r"}{" + sum_l_sq_str + r" + " + sum_u_str + r"} \\ "
        r"& \omega = " + omega_str + r" "
        r"\end{aligned}"
    )

    return {
        "omega": round(safe_float(omega), 3),
        "loadings": [round(safe_float(l), 3) for l in loadings],
        "uniquenesses": [round(safe_float(u), 3) for u in uniqueness],
        "sum_loadings": round(safe_float(sum_loadings), 3),
        "sum_loadings_sq": round(safe_float(sum_loadings_sq), 3),
        "sum_uniqueness": round(safe_float(sum_uniqueness), 3),
        "equation": r"\omega = \frac{(\sum \lambda_i)^2}{(\sum \lambda_i)^2 + \sum \psi_i}",
        "equation_values": r"\omega \approx \frac{(" + sum_l_str + r")^2}{(" + sum_l_str + r")^2 + " + sum_u_str + r"} = " + omega_str,
        "development": development
    }

@router.post("/analysis")
async def analyze_reliability(req: ReliabilityRequest):
    try:
        df = pd.DataFrame(req.data)[req.variables]
        
        cronbach = calculate_cronbach_alpha(df)
        
        try:
            omega = calculate_mcdonalds_omega(df)
        except Exception as e:
            # Fallback if Omega fails (e.g. non-convergence)
            traceback.print_exc()
            omega = {
                "omega": 0.0,
                "loadings": [],
                "uniquenesses": [],
                "error": str(e),
                "equation_values": "",
                "sum_loadings_sq": 0.0,
                "sum_uniqueness": 0.0
            }
            
        return {
            "cronbach": cronbach,
            "mcdonald_omega": omega
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en confiabilidad: {str(e)}")
