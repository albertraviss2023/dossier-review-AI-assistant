from __future__ import annotations

import os
import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dossier_review_ai_assistant.config import load_settings
from dossier_review_ai_assistant.data import load_dossiers, load_knowledge_wiki, build_evidence_chunks, build_knowledge_wiki_chunks
from dossier_review_ai_assistant.retrieval import HybridRetriever
from dossier_review_ai_assistant.orchestrator import ReasoningEngine
from dossier_review_ai_assistant.knowledge_graph import KnowledgeGraph

def run_messy_test():
    print("# Messy Query Smoke Test (Robustness & Attention)")
    settings = load_settings()
    os.environ["DOSSIER_MODEL_MODE"] = "mock"
    
    dossiers = load_dossiers(settings.data_jsonl_path)
    wiki = load_knowledge_wiki(settings.knowledge_wiki_path)
    target_dossier = next(d for d in dossiers if d["dossier_id"] == "DOS-9D9BC5402A")
    
    kg = KnowledgeGraph(dossiers)
    retriever = HybridRetriever(list(build_evidence_chunks(dossiers)) + list(build_knowledge_wiki_chunks(wiki)))
    engine = ReasoningEngine(model_id=settings.model_id, retriever=retriever)
    
    messy_queries = [
        ("summariz htis dossier and tell me risks about orgigin and manfacturer location", "review"),
        ("what are the amr concerns and aware class for DOS-9D9BC5402A?? also chemical simlarity", "review"),
        ("policy for reserve antibitocs", "wiki"),
        ("show me graf for approvals vs rejectns", "review"),
        ("define ssmr acronym", "review")
    ]
    
    for q_text, workspace in messy_queries:
        print(f"\n## User Query: \"{q_text}\"")
        result = engine.orchestrate(
            dossier=target_dossier, 
            question=q_text, 
            workspace=workspace,
            review_state={"summary_stats": kg.get_summary_stats()}
        )
        
        print(f"**Classified Intent:** {result.intent}")
        print(f"**Rationale:** {result.rationale[:300]}...")
        if result.chain_of_thought:
             print("**Chain of Thought (Steps):**")
             print(result.chain_of_thought)
        else:
             print("!! Warning: Chain of Thought is MISSING !!")
             
        if result.visualization_data:
            print("**Visualization Data present:** True")

if __name__ == "__main__":
    run_messy_test()
