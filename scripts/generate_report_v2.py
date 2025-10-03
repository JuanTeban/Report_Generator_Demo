#!/usr/bin/env python3
"""
Script para generar reportes con ReportAgent (Fase 2).
Interfaz compatible con generate_report.py original.
"""
import asyncio
import argparse
import json
import logging
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Importar tools para activar registro
import app.tools.implementations

from app.agents.specialized import ReportAgent
from app.config.settings import REPORTS_DIR

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

async def main(args):
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    logger.info(f"Generando reporte v2 (agente) para: {args.consultant}")
    
    try:
        # Crear agente
        agent = ReportAgent()
        
        # Generar reporte
        report = await agent.generate_report(
            consultant_name=args.consultant,
            report_type=args.type
        )
        
        # Guardar
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Reporte guardado en: {output_path}")
        else:
            timestamp = report.get('generated_at', '').replace(':', '-').split('.')[0]
            default_filename = f"{args.consultant.lower().replace(' ', '_')}_reporte_v2_{timestamp}.json"
            default_path = REPORTS_DIR / default_filename
            
            with open(default_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Reporte guardado en: {default_path}")
        
        if args.print_summary:
            print("\n" + "="*60)
            print("RESUMEN DEL REPORTE (v2 - AGENTE)")
            print("="*60)
            print(f"Consultor: {report['consultant']}")
            print(f"Fecha: {report['generated_at']}")
            print(f"Filas SQL: {report['data']['sql_rows']}")
            print(f"Evidencias: {report['data']['evidence_count']}")
            print(f"Gráficos: {len(report.get('charts', {}))}")
            print(f"Versión: {report['metadata'].get('version')}")
            print("\nSECCIONES:")
            for section_name, content in report.get('sections', {}).items():
                print(f"\n[{section_name.upper()}]")
                preview = content[:500] + "..." if len(content) > 500 else content
                print(preview)
        
        return 0
        
    except Exception as e:
        logger.error(f"Error generando reporte: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de reportes v2 (agentes)")
    
    parser.add_argument("--consultant", required=True, help="Nombre del consultor")
    parser.add_argument("--type", choices=["preview", "final"], default="preview")
    parser.add_argument("--output", help="Archivo de salida (JSON)")
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    
    args = parser.parse_args()
    
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)