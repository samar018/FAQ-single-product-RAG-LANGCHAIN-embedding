#!/usr/bin/env python3
"""
FAQ Bot with RAG using LangChain, HuggingFace Embeddings, FAISS, and OpenAI
"""
import os
import re
import json
import sys
import uuid
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple

from langchain.schema import Document
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from openai import OpenAI
import requests


# ============================================================
# Embedding Model
# ============================================================
def get_embedding_model():
    """Initialize HuggingFace embedding model"""
    # Using a fast and efficient model for general use
    # You can change this to "l3cube-pune/bengali-sentence-similarity-sbert" for Bengali-specific tasks
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={'device': 'cpu'},  # Use CPU by default
        encode_kwargs={'normalize_embeddings': True}  # Normalize embeddings
    )


# ============================================================
# Extract Q/A From PDF
# ============================================================
def extract_faq_from_pdf(pdf_path):
    """
    Extracts FAQ pairs from a PDF where format is:
    Q1 What is FinAI?
    FinAI is an AI-driven financial...
    """
    try:
        loader = PyPDFLoader(str(pdf_path))
        pages = loader.load()
    except Exception as e:
        print(f"Warning: PyPDFLoader failed ({e}), trying fallback...", file=sys.stderr)
        # Fallback to basic PDF extraction
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = '\n'.join([page.extract_text() for page in reader.pages])
                pages = [Document(page_content=text)]
            print("✓ Using PyPDF2 fallback successfully", file=sys.stderr)
        except Exception as e2:
            print(f"Error: Both PyPDFLoader and PyPDF2 failed: {e2}", file=sys.stderr)
            raise
    
    text = "\n".join([p.page_content for p in pages])
    
    faq_docs = []
    
    # Pattern 1: Q1, Q2, etc. followed by question and answer
    pattern1 = r"(Q\d+\s.+?)(?=\nQ\d+|\Z)"
    matches1 = re.findall(pattern1, text, flags=re.S)
    
    for block in matches1:
        lines = block.strip().split("\n")
        
        if len(lines) < 2:
            continue
        
        question = lines[0].strip()
        answer = "\n".join(lines[1:]).strip()
        
        # Clean up question (remove Q1, Q2, etc.)
        question = re.sub(r'^Q\d+\s*', '', question, flags=re.IGNORECASE).strip()
        
        if question and answer and len(answer) > 10:
            faq_docs.append(
                Document(
                    page_content=f"QUESTION: {question}\nANSWER: {answer}",
                    metadata={"question": question, "answer": answer}
                )
            )
    
    # Pattern 2: Numbered format: 1. Question? Answer
    if len(faq_docs) < 5:  # If we didn't get many, try other patterns
        # Try numbered format: 1. Question? Answer
        pattern2 = r"(\d+[\.\)]\s*[^?\n]+[?]?)\s*\n\s*([^\n]+(?:\n(?!\d+[\.\)])[^\n]+)*)"
        matches2 = re.findall(pattern2, text, re.MULTILINE)
        
        for match in matches2:
            question = match[0].strip().rstrip('?')
            answer = match[1].strip()
            if question and answer and len(answer) > 10:
                # Check if we already have this question
                if not any(doc.metadata.get("question", "").lower() == question.lower() for doc in faq_docs):
                    faq_docs.append(
                        Document(
                            page_content=f"QUESTION: {question}\nANSWER: {answer}",
                            metadata={"question": question, "answer": answer}
                        )
                    )
    
    # Pattern 3: Q: / A: format (if still not enough)
    if len(faq_docs) < 10:
        pattern3 = r"(?:Q|Question)[:\s]+(.+?)\s+(?:A|Answer)[:\s]+(.+?)(?=\n\s*(?:Q|Question|\d+[\.\)])|\Z)"
        matches3 = re.findall(pattern3, text, re.IGNORECASE | re.DOTALL)
        
        for match in matches3:
            question = match[0].strip().rstrip('?')
            answer = match[1].strip()
            if question and answer and len(answer) > 10:
                if not any(doc.metadata.get("question", "").lower() == question.lower() for doc in faq_docs):
                    faq_docs.append(
                        Document(
                            page_content=f"QUESTION: {question}\nANSWER: {answer}",
                            metadata={"question": question, "answer": answer}
                        )
                    )
    
    return faq_docs


# ============================================================
# Build Vector Store
# ============================================================
def build_vector_store(docs, embedding_model):
    """Build FAISS vector store from documents with L2 normalization"""
    if not docs:
        raise ValueError("No documents to build vector store from")
    
    # Build vector store with L2 normalization for cosine similarity
    return FAISS.from_documents(docs, embedding_model, normalize_L2=True)


# ============================================================
# Normalize Vectors
# ============================================================
def normalize(vec):
    """Normalize vectors for cosine similarity"""
    norm = np.linalg.norm(vec, axis=1, keepdims=True)
    norm[norm == 0] = 1  # Avoid division by zero
    return vec / norm


# ============================================================
# Retrieve With Confidence Score
# ============================================================
def retrieve(query, store, embedding_model, k=5):
    """Retrieve relevant documents with confidence scores"""
    try:
        # Get query embedding
        embed = embedding_model.embed_query(query)
        embed = np.array(embed, dtype="float32").reshape(1, -1)
        # Normalize query embedding for cosine similarity
        embed = normalize(embed)
        
        # Search in FAISS (returns L2 distances for normalized vectors)
        D, I = store.index.search(embed, k)
        
        results = []
        for score, idx in zip(D[0], I[0]):
            if idx == -1:
                continue
            
            doc = store.docstore._dict[idx]
            # Convert distance to similarity score
            # FAISS with normalize_L2=True returns L2 distances
            # For normalized vectors, distance ranges from 0 to 2
            # Convert to similarity: similarity = (2 - distance) / 2
            # This matches the original code pattern: (score + 1) / 2
            # where score is treated as distance in range [0, 2]
            similarity = float((2 - score) / 2)
            confidence = max(0.0, min(1.0, similarity))  # Clamp to [0, 1]
            
            results.append({
                "doc": doc,
                "confidence": confidence,
                "score": float(score),
                "question": doc.metadata.get("question", ""),
                "answer": doc.metadata.get("answer", "")
            })
        
        return results
    except Exception as e:
        print(f"Error in retrieval: {e}", file=sys.stderr)
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
        return []


# ============================================================
# OpenAI LLM Answering
# ============================================================
def get_openai_client():
    """Initialize OpenAI client"""
    github_token = os.environ.get("GITHUB_TOKEN", "")
    
    if github_token:
        return OpenAI(
            base_url="https://models.github.ai/inference",
            api_key=github_token
        )
    else:
        # Fallback to standard OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            return OpenAI(api_key=api_key)
        else:
            return None


def llm_answer(question, context, client=None, model="gpt-3.5-turbo"):
    """Generate answer using LLM"""
    if client is None:
        client = get_openai_client()
    
    if client is None:
        # Fallback: extract answer from context
        if "ANSWER:" in context:
            answer = context.split("ANSWER:")[-1].strip()
            return answer.split("\n")[0] if "\n" in answer else answer
        return "I couldn't generate an answer. Please check your OpenAI API key."
    
    system_prompt = (
        "You are a helpful assistant. Answer the user's question based ONLY on the provided context. "
        "If the answer is not found in the context, say: 'I don't know based on the provided information.' "
        "Be concise and accurate."
    )
    
    try:
        # Try GitHub models first
        if hasattr(client, 'base_url') and 'github.ai' in str(client.base_url):
            response = client.chat.completions.create(
                model="openai/gpt-4.1-nano",
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt + "\n\nContext:\n" + context},
                    {"role": "user", "content": question}
                ]
            )
        else:
            # Standard OpenAI
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt + "\n\nContext:\n" + context},
                    {"role": "user", "content": question}
                ]
            )
        
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM error: {e}", file=sys.stderr)
        # Fallback: extract from context
        if "ANSWER:" in context:
            answer = context.split("ANSWER:")[-1].strip()
            return answer.split("\n")[0] if "\n" in answer else answer
        return "I couldn't generate an answer at this time."


# ============================================================
# Human Escalation
# ============================================================
def escalate_to_human(question, escalation_url=None, escalation_headers=None):
    """Escalate question to human support"""
    if not escalation_url:
        return {
            "status": "escalated",
            "assigned_to": "Human Support Team",
            "question": question,
            "id": str(uuid.uuid4())
        }
    
    try:
        payload = {
            "user_question": question,
            "status": "queued_for_human_review"
        }
        resp = requests.post(escalation_url, json=payload, headers=escalation_headers or {}, timeout=6)
        try:
            return resp.json()
        except:
            return {"raw_response": resp.text, "id": str(uuid.uuid4())}
    except Exception as e:
        return {"error": str(e), "id": str(uuid.uuid4())}


# ============================================================
# Main RAG Logic
# ============================================================
def ask_faq_bot(question, vector_store, embedding_model, escalation_url=None, 
                escalation_headers=None, confidence_threshold=0.55, use_llm=True):
    """Main RAG function to answer questions"""
    
    # Retrieve relevant documents
    retrieved = retrieve(question, vector_store, embedding_model, k=5)
    
    if not retrieved:
        escalation = escalate_to_human(question, escalation_url, escalation_headers)
        return {
            "answer_text": "I don't know — I couldn't find relevant information in the documentation.",
            "confidence": {"score": 0.0, "label": "low"},
            "source_reference": "",
            "escalated_to_human": True,
            "escalation_request_id": escalation.get("id"),
            "context_used": []
        }
    
    best_result = retrieved[0]
    confidence_score = best_result["confidence"]
    
    # Determine confidence label
    if confidence_score >= 0.7:
        confidence_label = "high"
    elif confidence_score >= 0.4:
        confidence_label = "medium"
    else:
        confidence_label = "low"
    
    # Check if we should escalate
    should_escalate = confidence_score < confidence_threshold
    
    if should_escalate:
        escalation = escalate_to_human(question, escalation_url, escalation_headers)
        return {
            "answer_text": "I don't know — I'm not confident enough to answer this question.",
            "confidence": {"score": round(confidence_score, 4), "label": confidence_label},
            "source_reference": "",
            "escalated_to_human": True,
            "escalation_request_id": escalation.get("id"),
            "context_used": []
        }
    
    # Build context from retrieved documents
    context_parts = []
    for r in retrieved[:3]:  # Top 3 results
        context_parts.append(r["doc"].page_content)
    
    context = "\n\n".join(context_parts)
    
    # Generate answer
    if use_llm:
        client = get_openai_client()
        answer = llm_answer(question, context, client)
    else:
        # Fallback: use the best answer from metadata
        answer = best_result.get("answer", "")
        if not answer and "ANSWER:" in best_result["doc"].page_content:
            answer = best_result["doc"].page_content.split("ANSWER:")[-1].strip()
        if not answer:
            answer = best_result["doc"].page_content
    
    # Format answer
    if not answer.startswith("Based on the FAQ:"):
        answer = f"Based on the FAQ: {answer}"
    
    # Get source reference (best match)
    source_ref = ""
    if best_result.get("question") and best_result.get("answer"):
        source_ref = f"{best_result['question']} {best_result['answer']}"
    elif "QUESTION:" in best_result["doc"].page_content:
        source_ref = best_result["doc"].page_content.replace("QUESTION:", "").replace("ANSWER:", "").strip()
    else:
        source_ref = best_result["doc"].page_content[:300]
    
    return {
        "answer_text": answer,
        "confidence": {"score": round(confidence_score, 4), "label": confidence_label},
        "source_reference": source_ref,
        "escalated_to_human": False,
        "escalation_request_id": None,
        "context_used": context
    }


# ============================================================
# Main Execution
# ============================================================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="FAQ Bot with RAG")
    parser.add_argument("--doc", required=True, help="Path to FAQ PDF file")
    parser.add_argument("--escalation_url", default="http://localhost:5000/escalate", help="Escalation endpoint")
    parser.add_argument("--threshold", type=float, default=0.55, help="Confidence threshold")
    parser.add_argument("--use_llm", action="store_true", help="Use LLM for answer generation")
    args = parser.parse_args()
    
    pdf_path = Path(args.doc)
    
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)
    
    print("Loading PDF and extracting FAQs...")
    faq_docs = extract_faq_from_pdf(pdf_path)
    print(f"✓ Extracted {len(faq_docs)} FAQ pairs")
    
    print("Building vector store...")
    embedding_model = get_embedding_model()
    store = build_vector_store(faq_docs, embedding_model)
    print("✓ Vector store built")
    
    print("\nFAQ Bot ready! Type your questions (blank line to quit):\n")
    
    while True:
        try:
            question = input("Question: ").strip()
            if not question:
                break
            
            result = ask_faq_bot(
                question, 
                store, 
                embedding_model,
                escalation_url=args.escalation_url,
                confidence_threshold=args.threshold,
                use_llm=args.use_llm
            )
            
            print("\n" + json.dumps(result, indent=2))
            print(f"\nAnswer: {result['answer_text']}\n")
            
        except KeyboardInterrupt:
            print("\nBye!")
            break
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)

