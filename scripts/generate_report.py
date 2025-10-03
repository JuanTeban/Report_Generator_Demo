#!/usr/bin/env python3
"""
Script CLI para generar reportes.
Uso: python scripts/generate_report.py --consultant "NOMBRE_CONSULTOR"
"""

import asyncio
import argparse
import json
import logging
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app.core.report_generator.engine import ReportEngine
from app.config.settings import REPORTS_DIR

def setup_logging(verbose: bool = False):
    """Configura el logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

async def main(args):
    """Función principal."""
    
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    logger.info(f"Generando reporte para: {args.consultant}")
    
    try:
        engine = ReportEngine()
        
        report = await engine.generate_report(
            consultant_name=args.consultant,
            report_type=args.type
        )
        
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Reporte guardado en: {output_path}")
        else:
            timestamp = report.get('generated_at', '').replace(':', '-').split('.')[0]
            default_filename = f"{args.consultant.lower().replace(' ', '_')}_reporte_{timestamp}.json"
            default_path = REPORTS_DIR / default_filename
            
            with open(default_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Reporte guardado en: {default_path}")
        
        if args.print_summary:
            print("\n" + "="*60)
            print("RESUMEN DEL REPORTE")
            print("="*60)
            print(f"Consultor: {report['consultant']}")
            print(f"Fecha: {report['generated_at']}")
            print(f"Filas SQL: {report['data']['sql_rows']}")
            print(f"Evidencias: {report['data']['evidence_count']}")
            print(f"Gráficos generados: {len(report.get('charts', {}))}")
            print("\nSECCIONES:")
            for section_name, content in report.get('sections', {}).items():
                print(f"\n[{section_name.upper()}]")
                print(content[:500] + "..." if len(content) > 500 else content)
        
        return 0
        
    except Exception as e:
        logger.error(f"Error generando reporte: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generador de reportes CLI"
    )
    
    parser.add_argument(
        "--consultant",
        required=True,
        help="Nombre del consultor"
    )
    
    parser.add_argument(
        "--type",
        choices=["preview", "final"],
        default="preview",
        help="Tipo de reporte"
    )
    
    parser.add_argument(
        "--output",
        help="Archivo de salida (JSON). Si no se especifica, se usa data_store/reports/"
    )
    
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Imprimir resumen en consola"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Modo verbose"
    )
    
    args = parser.parse_args()
    
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)