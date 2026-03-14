from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import pandas as pd
import numpy as np
from factor_analyzer import FactorAnalyzer

router = APIRouter()

class ReliabilityRequest(BaseModel):
    data: List[Dict[str, Any]] # Array of records representing the dataframe
    variables: List[str] # Columns to analyze

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
     else:
         alpha = float((n_items / (n_items - 1)) * (1 - (sum_item_variances / total_variance)))
     
     # Calculate item-total correlations and alpha if item deleted
     item_stats = []
     mean_scores = df.mean().to_dict()
     std_scores = df.std().to_dict()
     
     total_scores = df.sum(axis=1)
     
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
             "mean": float(mean_scores[item]),
             "std_dev": float(std_scores[item]),
             "item_total_corr": item_total_corr,
             "alpha_if_deleted": alpha_del
         })
         
     equation = r"\alpha = \frac{k}{k-1} \left( 1 - \frac{\sum_{i=1}^{k} \sigma_i^2}{\sigma_T^2} \right)"
     equation_values = fr"\alpha = \frac{{{int(n_items)}}}{{{int(n_items)}-1}} \left( 1 - \frac{{{round(sum_item_variances, 3)}}}{{{round(total_variance, 3)}}} \right) = {round(alpha, 3)}"

     return {
         "alpha": round(alpha, 3),
         "n_items": int(n_items),
         "sum_item_variances": round(sum_item_variances, 3),
         "total_variance": round(total_variance, 3),
         "equation": equation,
         "equation_values": equation_values,
         "item_stats": item_stats
     }

def calculate_mcdonald_omega(df: pd.DataFrame):
     # Helper to clean NaN values for JS compatibility
     def sanitize_val(val):
         if isinstance(val, (float, np.float64, np.float32)) and (np.isnan(val) or np.isinf(val)):
             return 0.0
         try:
             return float(val)
         except:
             return val

     df = df.apply(pd.to_numeric, errors='coerce').dropna()
     
     if len(df.columns) < 3:
         return {
             "omega": 0.0, 
             "error": "El Omega de McDonald requiere al menos 3 variables.",
             "equation": r"\omega = \frac{(\sum \lambda_i)^2}{(\sum \lambda_i)^2 + \sum \psi_i}",
             "equation_values": r"\text{Error: Insuficientes variables (mínimo 3)}"
         }
     
     try:
         # Add numerical stability to prevent "Singular Matrix" crashes
         df_stable = df.astype(float).copy()
         np.random.seed(42)
         df_stable = df_stable + np.random.normal(0, 1e-8, df_stable.shape)

         # Perform 1-factor PAF to get loadings
         fa = FactorAnalyzer(n_factors=1, rotation=None, method='principal')
         fa.fit(df_stable)
         
         loadings = fa.loadings_[:, 0]
         uniqueness = fa.get_uniquenesses()
         
         sum_loadings = float(np.sum(loadings))
         sum_loadings_sq = float(sum_loadings ** 2)
         sum_uniqueness = float(np.sum(uniqueness))
         
         denominator = sum_loadings_sq + sum_uniqueness
         if denominator == 0:
             omega = 0.0
         else:
             omega = sum_loadings_sq / denominator
         
         # Correlation matrix
         corr_matrix = df.corr().fillna(0).round(3).to_dict('index')

         # Format item stats
         item_stats = []
         for i, col in enumerate(df.columns):
             item_stats.append({
                 "item": col,
                 "mean": sanitize_val(df[col].mean()),
                 "loading": sanitize_val(loadings[i]),
                 "uniqueness": sanitize_val(uniqueness[i])
             })
             
         # Sanitize
         omega_clean = sanitize_val(omega)
         sum_loadings_sq_clean = sanitize_val(sum_loadings_sq)
         sum_uniqueness_clean = sanitize_val(sum_uniqueness)

         equation = r"\omega = \frac{(\sum \lambda_i)^2}{(\sum \lambda_i)^2 + \sum \psi_i}"
         equation_values = fr"\omega = \frac{{{round(sum_loadings_sq_clean, 3)}}}{{{round(sum_loadings_sq_clean, 3)} + {round(sum_uniqueness_clean, 3)}}} = {round(omega_clean, 3)}"
         
         return {
             "omega": round(omega_clean, 3),
             "sum_loadings": round(sanitize_val(sum_loadings), 3),
             "sum_loadings_sq": round(sum_loadings_sq_clean, 3),
             "sum_uniqueness": round(sum_uniqueness_clean, 3),
             "method": "Principal Axis Factoring (1 factor)",
             "equation": equation,
             "equation_values": equation_values,
             "item_stats": item_stats,
             "correlations": corr_matrix,
             "n_cases": len(df)
         }
     except Exception as e:
         return {
             "omega": 0.0, 
             "error": str(e),
             "equation": r"\omega = \frac{(\sum \lambda_i)^2}{(\sum \lambda_i)^2 + \sum \psi_i}",
             "equation_values": fr"\text{{Error matemático: }} {str(e)[:50]}"
         }

@router.post("/analysis")
async def analyze_reliability(req: ReliabilityRequest):
    try:
        df = pd.DataFrame(req.data)[req.variables]
        
        cronbach_res = calculate_cronbach_alpha(df)
        omega_res = calculate_mcdonald_omega(df)
        
        return {
            "cronbach": cronbach_res,
            "mcdonald_omega": omega_res
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el análisis de confiabilidad: {str(e)}")
