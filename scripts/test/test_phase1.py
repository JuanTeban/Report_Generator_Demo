#!/usr/bin/env python3
"""
Test de Fase 1: Infraestructura base de tools y agentes
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

import app.tools.implementations

from app.tools.core import ToolRegistry
from app.agents.core import BaseAgent

async def test_tool_registry():
    print("\n" + "="*80)
    print("TEST 1: TOOL REGISTRY")
    print("="*80)
    
    # Verificar tools registradas
    tools = ToolRegistry.list_all()
    print(f"\n✓ Tools registradas: {len(tools)}")
    
    for tool in tools:
        print(f"\n  → {tool.name}")
        print(f"    Descripción: {tool.description}")
        schema = tool.to_llm_schema()
        print(f"    Parámetros: {list(schema['parameters'].get('properties', {}).keys())}")
    
    # Verificar schema LLM
    llm_schemas = ToolRegistry.get_llm_schemas()
    print(f"\n✓ Schemas LLM generados: {len(llm_schemas)}")

async def test_sql_tool():
    print("\n" + "="*80)
    print("TEST 2: SQL DATA EXTRACTION TOOL")
    print("="*80)
    
    tool = ToolRegistry.get("sql_data_extraction")
    
    if not tool:
        print("✗ Tool no encontrada")
        return
    
    print(f"\n✓ Tool encontrada: {tool.name}")
    print(f"  Ejecutando con consultor: YARLEN ASTRID ALVAREZ BUILES (203)")
    
    result = await tool.execute(consultant_name="YARLEN ASTRID ALVAREZ BUILES (203)")
    
    print(f"\n  Resultado:")
    print(f"    Success: {result.success}")
    print(f"    Rows: {result.metadata.get('row_count', 0)}")
    
    if result.success and result.data:
        print(f"    Primer defecto: {result.data[0].get('defectos', 'N/A')}")
    elif result.error:
        print(f"    Error: {result.error}")

async def test_evidence_tool():
    print("\n" + "="*80)
    print("TEST 3: EVIDENCE RETRIEVAL TOOL")
    print("="*80)
    
    tool = ToolRegistry.get("evidence_retrieval")
    
    if not tool:
        print("✗ Tool no encontrada")
        return
    
    print(f"\n✓ Tool encontrada: {tool.name}")
    print(f"  Ejecutando con defectos: ['8000002015', '8000001916']")
    
    result = await tool.execute(
        defect_ids=["8000002015", "8000001916"],
        consultant_name="YARLEN ASTRID ALVAREZ BUILES"
    )
    
    print(f"\n  Resultado:")
    print(f"    Success: {result.success}")
    print(f"    Total chunks: {result.metadata.get('total_chunks', 0)}")
    
    if result.success and result.data:
        for defect_id, sections in result.data.items():
            print(f"\n    Defecto {defect_id}:")
            print(f"      - Control: {len(sections.get('control', []))} chunks")
            print(f"      - Evidencia: {len(sections.get('evidencia', []))} chunks")
            print(f"      - Solución: {len(sections.get('solucion', []))} chunks")

async def main():
    print("\n" + "="*80)
    print("FASE 1: TEST DE INFRAESTRUCTURA BASE")
    print("="*80)
    
    await test_tool_registry()
    await test_sql_tool()
    await test_evidence_tool()
    
    print("\n" + "="*80)
    print("✓ FASE 1 COMPLETADA")
    print("="*80)
    print("\nPróximo paso: Implementar Fase 2 (ReportAgent)")

if __name__ == "__main__":
    asyncio.run(main())