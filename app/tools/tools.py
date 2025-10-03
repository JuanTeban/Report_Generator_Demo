import duckdb
import json
from app.config.settings_etl import DUCKDB_PATH
from typing import Dict

class DuckDBTool:
    """Herramienta para ejecutar consultas en DuckDB."""
    
    def invoke(self, params: Dict[str, str]) -> str:
        """Ejecuta una consulta SQL y retorna JSON."""
        sql = params.get("sql_query", "")
        
        try:
            con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
            result = con.execute(sql).fetchdf()
            con.close()
            
            return json.dumps({
                "success": True,
                "json_data": result.to_dict(orient="records"),
                "row_count": len(result)
            })
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "json_data": []
            })

execute_duckdb_query = DuckDBTool()