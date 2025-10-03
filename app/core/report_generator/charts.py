import pandas as pd
from typing import Dict, Any, Optional

class ChartBuilder:
    """Constructor de gráficos para reportes."""
    
    def build_chart(self, df: pd.DataFrame, column: str, chart_type: str) -> Optional[Dict[str, Any]]:
        """
        Construye un gráfico en formato Plotly JSON.
        """
        if column not in df.columns:
            return None
        
        if chart_type == "pie":
            return self._build_pie_chart(df, column)
        elif chart_type == "bar":
            return self._build_bar_chart(df, column)
        else:
            return None
    
    def _build_pie_chart(self, df: pd.DataFrame, column: str) -> Dict[str, Any]:
        """Genera un gráfico de torta."""
        counts = df[column].value_counts()
        
        return {
            "data": [{
                "type": "pie",
                "labels": counts.index.tolist(),
                "values": counts.values.tolist(),
                "hole": 0.4
            }],
            "layout": {
                "title": f"Distribución por {column}",
                "margin": {"t": 40, "b": 40, "l": 40, "r": 40}
            }
        }
    
    def _build_bar_chart(self, df: pd.DataFrame, column: str) -> Dict[str, Any]:
        """Genera un gráfico de barras."""
        counts = df[column].value_counts()
        
        return {
            "data": [{
                "type": "bar",
                "x": counts.index.tolist(),
                "y": counts.values.tolist()
            }],
            "layout": {
                "title": f"Cantidad por {column}",
                "xaxis": {"title": column},
                "yaxis": {"title": "Cantidad"},
                "margin": {"t": 40, "b": 80, "l": 60, "r": 40}
            }
        }