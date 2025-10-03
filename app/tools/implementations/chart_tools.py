# app/tools/implementations/chart_tools.py
import pandas as pd
from pydantic import Field
from typing import List, Dict, Any

from app.tools.core import BaseTool, ToolInput, ToolOutput, register_tool
from app.core.report_generator.charts import ChartBuilder

@register_tool
class ChartGenerationTool(BaseTool):
    """
    Genera gráficos a partir de datos SQL.
    Reutiliza ChartBuilder existente.
    """
    
    class Input(ToolInput):
        sql_data: List[Dict] = Field(..., description="Datos SQL para visualizar")
    
    @property
    def name(self) -> str:
        return "chart_generation"
    
    @property
    def description(self) -> str:
        return "Genera gráficos (pie, bar) basados en los datos SQL del reporte"
    
    @property
    def input_schema(self) -> type[ToolInput]:
        return self.Input
    
    def __init__(self):
        self.chart_builder = ChartBuilder()
    
    async def execute(self, sql_data: List[Dict]) -> ToolOutput:
        try:
            if not sql_data:
                return ToolOutput(
                    success=False,
                    data={},
                    error="No hay datos para generar gráficos"
                )
            
            df = pd.DataFrame(sql_data)
            charts = {}
            
            # Configuración de gráficos
            chart_configs = [
                ("estado_distribution", "estado_de_defecto", "pie"),
                ("module_distribution", "modulo", "bar"),
                ("blocker_status", "bloqueante_escenarios", "pie"),
                ("age_by_defect", "antiguedad_del_defecto_promedio_en_dias", "bar")
            ]
            
            for chart_name, column, chart_type in chart_configs:
                if column in df.columns:
                    chart = self.chart_builder.build_chart(df, column, chart_type)
                    if chart:
                        charts[chart_name] = chart
            
            return ToolOutput(
                success=True,
                data=charts,
                metadata={
                    "total_charts": len(charts),
                    "chart_names": list(charts.keys())
                }
            )
            
        except Exception as e:
            return ToolOutput(
                success=False,
                data={},
                error=f"Error generando gráficos: {str(e)}"
            )