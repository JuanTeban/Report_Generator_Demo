#!/usr/bin/env python3
"""
Test Fase 2: Comparación ReportEngine vs ReportAgent
"""
import asyncio
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# Importar tools
import app.tools.implementations

from app.core.report_generator.engine import ReportEngine
from app.agents.specialized import ReportAgent

async def test_report_comparison():
    print("\n" + "="*80)
    print("TEST: COMPARACIÓN ReportEngine vs ReportAgent")
    print("="*80)
    
    consultant = "YARLEN ASTRID ALVAREZ BUILES (203)"
    
    # Generar con engine original
    print(f"\n1. Generando con ReportEngine (original)...")
    engine = ReportEngine()
    report_old = await engine.generate_report(consultant)
    
    print(f"   ✓ Reporte generado")
    print(f"   - Filas SQL: {report_old['data']['sql_rows']}")
    print(f"   - Evidencias: {report_old['data']['evidence_count']}")
    print(f"   - Gráficos: {len(report_old.get('charts', {}))}")
    
    # Generar con agente
    print(f"\n2. Generando con ReportAgent (v2)...")
    agent = ReportAgent()
    report_new = await agent.generate_report(consultant)
    
    print(f"   ✓ Reporte generado")
    print(f"   - Filas SQL: {report_new['data']['sql_rows']}")
    print(f"   - Evidencias: {report_new['data']['evidence_count']}")
    print(f"   - Gráficos: {len(report_new.get('charts', {}))}")
    
    # Comparar
    print(f"\n3. Comparando resultados...")
    
    # Comparar datos
    if report_old['data']['sql_rows'] == report_new['data']['sql_rows']:
        print(f"   ✓ SQL rows: IGUALES ({report_old['data']['sql_rows']})")
    else:
        print(f"   ✗ SQL rows: DIFERENTES (old={report_old['data']['sql_rows']}, new={report_new['data']['sql_rows']})")
    
    # Comparar secciones
    old_summary_len = len(report_old['sections'].get('summary', ''))
    new_summary_len = len(report_new['sections'].get('summary', ''))
    
    if abs(old_summary_len - new_summary_len) < 100:  # Tolerancia
        print(f"   ✓ Summary: SIMILAR (old={old_summary_len}, new={new_summary_len})")
    else:
        print(f"   ⚠ Summary: DIFERENTE (old={old_summary_len}, new={new_summary_len})")
    
    # Comparar gráficos
    old_charts = set(report_old.get('charts', {}).keys())
    new_charts = set(report_new.get('charts', {}).keys())
    
    if old_charts == new_charts:
        print(f"   ✓ Gráficos: IGUALES ({len(old_charts)} charts)")
    else:
        print(f"   ⚠ Gráficos: DIFERENTES")
        print(f"     Old: {old_charts}")
        print(f"     New: {new_charts}")
    
    # Guardar para inspección
    output_dir = Path("data_store/reports/comparison")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / "report_old.json", "w", encoding="utf-8") as f:
        json.dump(report_old, f, indent=2, ensure_ascii=False)
    
    with open(output_dir / "report_new.json", "w", encoding="utf-8") as f:
        json.dump(report_new, f, indent=2, ensure_ascii=False)
    
    print(f"\n   ℹ Reportes guardados en: {output_dir}")

async def main():
    print("\n" + "="*80)
    print("FASE 2: TEST DE REPORT AGENT")
    print("="*80)
    
    await test_report_comparison()
    
    print("\n" + "="*80)
    print("✓ FASE 2 COMPLETADA")
    print("="*80)
    print("\nPróximos pasos:")
    print("  1. Revisar reportes en data_store/reports/comparison/")
    print("  2. Si son similares, migrar gradualmente")
    print("  3. Usar ReportAgent como interfaz principal")

if __name__ == "__main__":
    asyncio.run(main())