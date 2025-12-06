#!/usr/bin/env python3
"""
FAQ Bot API Server - Web API for FAQ bot functionality with RAG
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Import RAG-based FAQ bot functions
from faq_bot_rag import (
    extract_faq_from_pdf,
    build_vector_store,
    get_embedding_model,
    ask_faq_bot
)

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)  # Enable CORS for all routes

# Global variables to store loaded document and vector store
vector_store = None
embedding_model = None
doc_path = None
escalation_url = None
escalation_headers = {}
confidence_threshold = 0.55
use_llm = True

def convert_threshold_to_float(threshold):
    """Convert threshold from string ('low', 'medium', 'high') or float to float"""
    if isinstance(threshold, (int, float)):
        return float(threshold)
    
    if isinstance(threshold, str):
        threshold_lower = threshold.lower()
        if threshold_lower == "low":
            return 0.3
        elif threshold_lower == "medium":
            return 0.55
        elif threshold_lower == "high":
            return 0.7
        else:
            # Try to convert string to float
            try:
                return float(threshold)
            except ValueError:
                return 0.55  # Default to medium
    
    return 0.55  # Default

@app.route("/")
def index():
    """Serve the frontend HTML"""
    return send_from_directory('static', 'index.html')

@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "document_loaded": vector_store is not None,
        "document_path": doc_path,
        "embedding_model": "HuggingFace + FAISS",
        "llm_enabled": use_llm
    }), 200

@app.route("/api/initialize", methods=["POST"])
def initialize():
    """Initialize the FAQ bot with a document"""
    global vector_store, embedding_model, doc_path, escalation_url, escalation_headers, confidence_threshold, use_llm
    
    try:
        data = request.get_json() or {}
        doc_path = data.get("doc_path")
        escalation_url = data.get("escalation_url", "http://localhost:5000/escalate")
        threshold = data.get("threshold", 0.55)
        use_llm_flag = data.get("use_llm", True)
        
        if not doc_path:
            return jsonify({"error": "doc_path is required"}), 400
        
        pdf_path = Path(doc_path)
        if not pdf_path.exists():
            return jsonify({"error": f"Document not found: {doc_path}"}), 404
        
        # Load and process document using RAG approach
        print(f"Loading document: {doc_path}")
        faq_docs = extract_faq_from_pdf(pdf_path)
        
        if not faq_docs:
            return jsonify({"error": "No FAQ pairs found in document. Please check the PDF format."}), 400
        
        print(f"Extracted {len(faq_docs)} FAQ pairs")
        
        # Build embedding model and vector store
        embedding_model = get_embedding_model()
        vector_store = build_vector_store(faq_docs, embedding_model)
        
        # Convert threshold (handles both string and numeric)
        confidence_threshold = convert_threshold_to_float(threshold)
        use_llm = bool(use_llm_flag)
        
        return jsonify({
            "status": "success",
            "message": f"Document loaded successfully",
            "faq_pairs": len(faq_docs),
            "document_path": str(doc_path),
            "confidence_threshold": confidence_threshold,
            "llm_enabled": use_llm
        }), 200
        
    except Exception as e:
        import traceback
        print(f"Error initializing: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return jsonify({"error": str(e)}), 500

@app.route("/api/ask", methods=["POST"])
def ask():
    """Handle a question and return an answer using RAG"""
    global vector_store, embedding_model, escalation_url, escalation_headers, confidence_threshold, use_llm
    
    if vector_store is None or embedding_model is None:
        return jsonify({"error": "Document not initialized. Please initialize first."}), 400
    
    try:
        data = request.get_json() or {}
        user_question = data.get("question", "").strip()
        
        if not user_question:
            return jsonify({"error": "question is required"}), 400
        
        # Use RAG to get answer
        result = ask_faq_bot(
            user_question,
            vector_store,
            embedding_model,
            escalation_url=escalation_url,
            escalation_headers=escalation_headers,
            confidence_threshold=confidence_threshold,
            use_llm=use_llm
        )
        
        return jsonify(result), 200
        
    except Exception as e:
        import traceback
        print(f"Error in ask: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return jsonify({"error": str(e)}), 500

@app.route("/api/config", methods=["GET", "POST"])
def config():
    """Get or update configuration"""
    global escalation_url, confidence_threshold, use_llm
    
    if request.method == "GET":
        return jsonify({
            "escalation_url": escalation_url,
            "confidence_threshold": confidence_threshold,
            "use_llm": use_llm,
            "document_loaded": vector_store is not None
        }), 200
    
    # POST - update config
    try:
        data = request.get_json() or {}
        if "escalation_url" in data:
            escalation_url = data["escalation_url"]
        if "threshold" in data:
            confidence_threshold = convert_threshold_to_float(data["threshold"])
        if "use_llm" in data:
            use_llm = bool(data["use_llm"])
        
        return jsonify({
            "status": "success",
            "escalation_url": escalation_url,
            "confidence_threshold": confidence_threshold,
            "use_llm": use_llm
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="FAQ Bot API Server with RAG")
    parser.add_argument("--doc", help="Path to FAQ PDF file")
    parser.add_argument("--escalation_url", default="http://localhost:5000/escalate", help="Escalation endpoint URL")
    parser.add_argument("--threshold", type=float, default=0.55, help="Confidence threshold (0.0-1.0)")
    parser.add_argument("--use_llm", action="store_true", help="Use LLM for answer generation")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()
    
    # Auto-initialize if doc path provided
    if args.doc:
        pdf_path = Path(args.doc)
        if pdf_path.exists():
            escalation_url = args.escalation_url
            confidence_threshold = args.threshold
            use_llm = args.use_llm
            try:
                print(f"Loading document: {args.doc}")
                faq_docs = extract_faq_from_pdf(pdf_path)
                print(f"Extracted {len(faq_docs)} FAQ pairs")
                
                embedding_model = get_embedding_model()
                vector_store = build_vector_store(faq_docs, embedding_model)
                # Make them global
                globals()['embedding_model'] = embedding_model
                globals()['vector_store'] = vector_store
                doc_path = str(args.doc)
                print(f"✓ Document loaded: {len(faq_docs)} FAQ pairs")
            except Exception as e:
                import traceback
                print(f"Error loading document: {e}", file=sys.stderr)
                print(traceback.format_exc(), file=sys.stderr)
        else:
            print(f"Warning: Document not found: {args.doc}", file=sys.stderr)
    
    print(f"Starting FAQ Bot API Server on http://{args.host}:{args.port}")
    print(f"Open http://localhost:{args.port} in your browser")
    app.run(host=args.host, port=args.port, debug=True)

