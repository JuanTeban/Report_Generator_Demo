# scripts/test/test_structured_retrieval.py
#!/usr/bin/env python3

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from app.core.report_generator.retrieval import RAGRetriever

async def test_structured_retrieval():
    print("\n" + "="*80)
    print("TEST: RECUPERACIÓN ESTRUCTURADA DE EVIDENCIA")
    print("="*80)
    
    retriever = RAGRetriever()
    
    # IDs de prueba (ajustar según tus datos)
    test_defect_ids = ["8000002015", "8000001916"]
    test_responsable = "YARLEN ASTRID ALVAREZ BUILES"
    
    print(f"\n📋 Probando recuperación para:")
    print(f"   - Defectos: {test_defect_ids}")
    print(f"   - Responsable: {test_responsable}")
    
    evidence = await retriever.get_defect_evidence_structured(
        defect_ids=test_defect_ids,
        responsable=test_responsable,
        chunks_per_defect=20
    )
    
    print("\n" + "="*80)
    print("RESULTADOS")
    print("="*80)
    
    for defect_id, sections in evidence.items():
        print(f"\n🔍 DEFECTO: {defect_id}")
        print("-"*80)
        
        for section_name, chunks in sections.items():
            print(f"\n  📁 Sección: {section_name}")
            print(f"     Chunks encontrados: {len(chunks)}")
            
            if chunks:
                # Mostrar primer chunk como ejemplo
                first_chunk = chunks[0]
                content_preview = first_chunk["content"][:200]
                print(f"     Preview: {content_preview}...")
                print(f"     Metadata: {first_chunk['metadata'].get('section_title', 'N/A')}")
            else:
                print(f"     ⚠️  No se encontraron chunks para esta sección")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    asyncio.run(test_structured_retrieval())