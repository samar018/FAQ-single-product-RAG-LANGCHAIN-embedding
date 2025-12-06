#!/usr/bin/env python3
"""
FAQ Support Bot (single product) - CLI version
Features:
- Loads a single FAQ / docs file (PDF, markdown, or plain text).
- Automatically extracts text from PDF files.
- Splits doc into chunks (by markdown headings and paragraphs).
- Builds a TF-IDF index (fast, deterministic).
- On each user question:
  - retrieves top-k relevant snippets (returns scores)
  - constructs an explicit prompt (inspectable)
  - generates a deterministic grounded answer (no external LLM required)
  - computes confidence score & label (inspectable function)
  - if confidence < threshold, POSTs escalation payload to provided endpoint
  - prints structured JSON output for the turn
Usage:
  python faq_bot_CLI.py --doc sample_faq.pdf --escalation_url http://localhost:5000/escalate
  python faq_bot_CLI.py --doc sample_faq.md --escalation_url http://localhost:5000/escalate
Optional:
  - provide --threshold [low|medium|high] to change escalation cutoff
  - set OPENAI_API_KEY env and modify call_llm to use OpenAI for generation
"""
import argparse
import json
import os
import re
import sys
import uuid
from typing import List, Dict, Any, Tuple

import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ------------------------------
# Document loading & chunking
# ------------------------------
def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from PDF file using available PDF library.
    Tries PyPDF2, then pdfplumber, then pypdf.
    """
    text = ""
    
    # Try PyPDF2
    try:
        import PyPDF2
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = '\n'.join([page.extract_text() for page in reader.pages])
            if text.strip():
                return text
    except ImportError:
        pass
    except Exception as e:
        print(f"Warning: PyPDF2 extraction failed: {e}", file=sys.stderr)
    
    # Try pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = '\n'.join([page.extract_text() or '' for page in pdf.pages])
            if text.strip():
                return text
    except ImportError:
        pass
    except Exception as e:
        print(f"Warning: pdfplumber extraction failed: {e}", file=sys.stderr)
    
    # Try pypdf (newer version of PyPDF2)
    try:
        import pypdf
        with open(pdf_path, 'rb') as file:
            reader = pypdf.PdfReader(file)
            text = '\n'.join([page.extract_text() for page in reader.pages])
            if text.strip():
                return text
    except ImportError:
        pass
    except Exception as e:
        print(f"Warning: pypdf extraction failed: {e}", file=sys.stderr)
    
    # If all methods failed
    if not text.strip():
        print("Error: Could not extract text from PDF. Please install a PDF library:", file=sys.stderr)
        print("  pip install PyPDF2", file=sys.stderr)
        print("  or: pip install pdfplumber", file=sys.stderr)
        print("  or: pip install pypdf", file=sys.stderr)
        sys.exit(1)
    
    return text

def load_document(path: str) -> str:
    """
    Load document from file. Supports PDF, markdown, and plain text files.
    Automatically detects file type by extension.
    """
    if not os.path.exists(path):
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    
    # Check if it's a PDF file
    if path.lower().endswith('.pdf'):
        print(f"Detected PDF file. Extracting text...")
        text = extract_text_from_pdf(path)
        print(f"✓ Successfully extracted {len(text)} characters from PDF")
        return text
    
    # For text/markdown files
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        # Try with different encoding
        try:
            with open(path, "r", encoding="latin-1") as f:
                return f.read()
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)

def chunk_document(text: str) -> List[Dict[str, Any]]:
    """
    Split document into chunks optimized for FAQ documents.
    Tries to create one chunk per Q&A pair for better retrieval.
    Returns list of dicts: {id, section_title, content}
    """
    # Clean up text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    chunks = []
    min_chunk_size = 30  # Lowered minimum for FAQ items
    
    # First, try to split by Q&A patterns (most common in FAQ docs)
    # Pattern: Number. Question? Answer text
    qa_pattern = re.compile(
        r'(\d+)[\.\)]\s*([^?\n]+[?]?)\s*\n\s*([^\n]+(?:\n(?!\d+[\.\)])[^\n]+)*)',
        re.MULTILINE | re.IGNORECASE
    )
    
    qa_matches = list(qa_pattern.finditer(text))
    
    if qa_matches:
        # Found numbered Q&A format
        for match in qa_matches:
            q_num = match.group(1)
            question = match.group(2).strip()
            answer = match.group(3).strip()
            
            # Clean up question
            question = re.sub(r'^\s*(Q|Question)[:\s]*', '', question, flags=re.IGNORECASE)
            question = question.strip()
            
            # Combine Q&A
            content = f"{question} {answer}".strip()
            
            if len(content) >= min_chunk_size:
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "section_title": f"Q{q_num}: {question[:60]}",
                    "content": content
                })
    
    # If no Q&A patterns found, try Q: / A: format
    if not chunks:
        qa_pattern2 = re.compile(
            r'(?:Q|Question)[:\s]+(.+?)\s*(?:A|Answer)[:\s]+(.+?)(?=\n\s*(?:Q|Question|$))',
            re.MULTILINE | re.IGNORECASE | re.DOTALL
        )
        qa_matches2 = list(qa_pattern2.finditer(text))
        
        if qa_matches2:
            for idx, match in enumerate(qa_matches2, 1):
                question = match.group(1).strip()
                answer = match.group(2).strip()
                content = f"{question} {answer}".strip()
                
                if len(content) >= min_chunk_size:
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "section_title": f"Q{idx}: {question[:60]}",
                        "content": content
                    })
    
    # Fallback: split by paragraphs or lines
    if not chunks:
        lines = text.split("\n")
        buffer = []
        cur_title = "FAQ"
        
        for i, ln in enumerate(lines):
            line_stripped = ln.strip()
            
            # Detect questions (lines ending with ?)
            if line_stripped.endswith('?') and len(line_stripped) > 10:
                if buffer:
                    content = "\n".join(buffer).strip()
                    if len(content) >= min_chunk_size:
                        chunks.append({
                            "id": str(uuid.uuid4()),
                            "section_title": cur_title,
                            "content": content
                        })
                buffer = [ln]
                cur_title = line_stripped[:80]
            # Blank line => paragraph boundary
            elif line_stripped == "":
                if buffer and len("\n".join(buffer).strip()) >= min_chunk_size:
                    content = "\n".join(buffer).strip()
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "section_title": cur_title,
                        "content": content
                    })
                    buffer = []
            else:
                buffer.append(ln)
        
        # Flush remaining
        if buffer:
            content = "\n".join(buffer).strip()
            if len(content) >= min_chunk_size:
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "section_title": cur_title,
                    "content": content
                })
    
    # Final fallback: split by double newlines
    if not chunks:
        paragraphs = re.split(r'\n\s*\n+', text)
        for para in paragraphs:
            para = para.strip()
            if len(para) >= min_chunk_size:
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "section_title": "FAQ",
                    "content": para
                })
    
    # Last resort: use entire text
    if not chunks:
        chunks.append({
            "id": str(uuid.uuid4()),
            "section_title": "Document",
            "content": text.strip()
        })
    
    return chunks

# ------------------------------
# Retriever: TF-IDF + cosine
# ------------------------------
class TfIdfRetriever:
    def __init__(self, chunks: List[Dict[str, Any]]):
        texts = [c["content"] for c in chunks]
        num_docs = len(texts)
        
        # Adaptive settings based on number of documents
        # For small document sets, use more lenient parameters
        if num_docs < 10:
            # Small document set - use simpler settings
            self.vectorizer = TfidfVectorizer(
                stop_words="english",
                ngram_range=(1, 2),  # Bigrams only for small sets
                max_features=5000,
                min_df=1,
                max_df=1.0  # Don't filter any terms
            )
        else:
            # Larger document set - can use more sophisticated settings
            self.vectorizer = TfidfVectorizer(
                stop_words="english", 
                ngram_range=(1, 3),  # Include trigrams for better phrase matching
                max_features=20000,   # Increased for better vocabulary coverage
                min_df=1,              # Include all terms
                max_df=0.95            # Exclude very common terms
            )
        
        self.doc_vectors = self.vectorizer.fit_transform(texts)
        self.chunks = chunks

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve top_k most relevant chunks with improved query processing."""
        # Normalize query - remove question marks, lowercase
        normalized_query = query.lower().strip().rstrip('?')
        
        # Transform query
        qv = self.vectorizer.transform([normalized_query])
        sims = cosine_similarity(qv, self.doc_vectors).flatten()
        
        # Get ranked results
        ranked = sorted(((i, float(s)) for i, s in enumerate(sims)), key=lambda x: x[1], reverse=True)
        
        results = []
        for idx, score in ranked[:top_k]:
            c = self.chunks[idx]
            results.append({
                "chunk_id": c["id"],
                "section_title": c["section_title"],
                "content": c["content"],
                "score": score
            })
        
        # If top score is very low, try exact keyword matching as fallback
        if results and results[0]["score"] < 0.05:
            query_words = set(normalized_query.split())
            keyword_scores = []
            
            for i, chunk in enumerate(self.chunks):
                chunk_lower = chunk["content"].lower()
                # Count matching words
                matches = sum(1 for word in query_words if len(word) > 3 and word in chunk_lower)
                if matches > 0:
                    keyword_scores.append((i, matches / len(query_words)))
            
            if keyword_scores:
                keyword_scores.sort(key=lambda x: x[1], reverse=True)
                # Use keyword matching results if they're better
                if keyword_scores[0][1] > 0.3:  # At least 30% word match
                    results = []
                    for idx, score in keyword_scores[:top_k]:
                        c = self.chunks[idx]
                        results.append({
                            "chunk_id": c["id"],
                            "section_title": c["section_title"],
                            "content": c["content"],
                            "score": float(score)  # Normalize to 0-1 range
                        })
        
        return results

# ------------------------------
# Prompt construction (inspectable)
# ------------------------------
def build_prompt(retrieved: List[Dict[str, Any]], user_question: str) -> str:
    instructions = (
        "You are an assistant whose only knowledge source is the DOCUMENT SNIPPETS below.\n"
        "Answer using ONLY the snippets. Cite the snippet's section in square brackets when used.\n"
        "If the snippets do not contain enough information, say you are unsure and recommend escalation.\n\n"
    )
    snippet_texts = []
    for i, s in enumerate(retrieved, start=1):
        snippet_texts.append(f"--- SNIPPET {i} [section: {s['section_title']}] (score={s['score']:.4f}) ---\n{s['content']}\n")
    prompt = instructions + "\n".join(snippet_texts) + f"\nUser question: {user_question}\nAnswer:"
    return prompt

# ------------------------------
# LLM / Answering (deterministic fallback)
# ------------------------------
def extract_clean_content(content: str) -> str:
    """
    Clean up content by removing document headers, metadata, and formatting artifacts.
    """
    # Remove common PDF extraction artifacts
    content = re.sub(r'FinAI\s+Comprehensive\s+FAQ[:\s]*', '', content, flags=re.IGNORECASE)
    content = re.sub(r'100\s+Q&A\s+for\s+RAG\s+Training\s+Data', '', content, flags=re.IGNORECASE)
    content = re.sub(r'FinAIDocumentation\s+December\d+,\s*\d+', '', content, flags=re.IGNORECASE)
    content = re.sub(r'Thisdocumentcontains[^\n]*', '', content, flags=re.IGNORECASE)
    content = re.sub(r'formattedfor\s+useastraining', '', content, flags=re.IGNORECASE)
    
    # Remove excessive whitespace
    content = re.sub(r'\s+', ' ', content)
    content = re.sub(r'\n\s*\n+', '\n', content)
    
    return content.strip()

def extract_faq_pair(content: str) -> tuple:
    """
    Try to extract a Q&A pair from content with multiple pattern matching.
    Returns (question, answer) or (None, content) if no clear Q&A found.
    """
    # Pattern 1: Number. Question? Answer
    pattern1 = re.search(r'(\d+)[\.\)]\s*([^?\n]+[?]?)\s+([^\n]+(?:\n(?!\d+[\.\)])[^\n]+)*)', content, re.IGNORECASE | re.DOTALL)
    if pattern1:
        question = pattern1.group(2).strip().rstrip('?')
        answer = pattern1.group(3).strip()
        question = re.sub(r'\s+', ' ', question)
        answer = re.sub(r'\s+', ' ', answer)
        if len(answer) > 300:
            answer = answer[:300].rsplit('.', 1)[0] + '.'
        return (question, answer)
    
    # Pattern 2: Q: or Question: ... A: or Answer: ...
    pattern2 = re.search(r'(?:Q|Question)[:\s]+(.+?)\s+(?:A|Answer)[:\s]+(.+?)(?=\n\s*(?:Q|Question|\d+[\.\)]|$))', content, re.IGNORECASE | re.DOTALL)
    if pattern2:
        question = pattern2.group(1).strip().rstrip('?')
        answer = pattern2.group(2).strip()
        question = re.sub(r'\s+', ' ', question)
        answer = re.sub(r'\s+', ' ', answer)
        if len(answer) > 300:
            answer = answer[:300].rsplit('.', 1)[0] + '.'
        return (question, answer)
    
    # Pattern 3: Question ending with ? followed by answer
    pattern3 = re.search(r'([^?\n]+[?])\s+([^\n]+(?:\n[^\n]+)*)', content, re.DOTALL)
    if pattern3:
        question = pattern3.group(1).strip().rstrip('?')
        answer = pattern3.group(2).strip()
        # Only use if question is reasonable length
        if 10 <= len(question) <= 200:
            question = re.sub(r'\s+', ' ', question)
            answer = re.sub(r'\s+', ' ', answer)
            if len(answer) > 300:
                answer = answer[:300].rsplit('.', 1)[0] + '.'
            return (question, answer)
    
    return (None, content)

def generate_answer_from_snippets(retrieved: List[Dict[str, Any]], user_question: str) -> str:
    """
    Generate clean, focused answers from retrieved snippets.
    Tries to extract Q&A pairs and format them nicely.
    """
    if not retrieved:
        return "I couldn't find information about that in the product documentation."
    
    top = retrieved[0]
    # Lower threshold for PDF content (PDF extraction may have lower scores)
    if top["score"] < 0.01:
        return "I don't know — the documentation doesn't contain information to answer that."
    
    # Try to find a clear Q&A pair in the top result
    top_content = extract_clean_content(top["content"])
    question, answer = extract_faq_pair(top_content)
    
    if question and answer:
        # Found a clear Q&A pair
        return f"Based on the FAQ: {question} {answer}"
    
    # Fallback: extract relevant sentences from content
    content = top_content
    sentences = re.split(r'[.!?]+\s+', content)
    question_words = set(user_question.lower().split())
    
    # Score sentences by keyword overlap
    scored_sentences = []
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 20:  # Skip very short sentences
            continue
        sent_lower = sent.lower()
        score = sum(1 for word in question_words if word in sent_lower and len(word) > 3)
        if score > 0:
            scored_sentences.append((score, sent))
    
    if scored_sentences:
        scored_sentences.sort(reverse=True)
        # Use top 2-3 most relevant sentences
        relevant_sentences = [s[1] for s in scored_sentences[:3]]
        answer_text = ". ".join(relevant_sentences)
        if len(answer_text) > 400:
            answer_text = answer_text[:400].rsplit(".", 1)[0] + "."
        return f"Based on the FAQ: {answer_text}"
    
    # Final fallback: use beginning of content
    if len(content) > 400:
        content = content[:400].rsplit(".", 1)[0] + "."
    return f"Based on the FAQ: {content}"

# ------------------------------
# Confidence estimation & escalation decision
# ------------------------------
def compute_confidence(retrieved: List[Dict[str, Any]]) -> Tuple[float, str]:
    """
    Improved confidence calculation for PDF content.
    PDF text extraction often results in lower similarity scores, so thresholds are adjusted.
    """
    if not retrieved:
        return 0.0, "low"
    
    top_score = max(0.0, min(1.0, retrieved[0]["score"]))
    
    # Adjusted thresholds for PDF content (typically lower scores)
    # Also consider score spread between top results
    if len(retrieved) > 1:
        score_spread = top_score - retrieved[1]["score"]
        # Boost confidence if top result is significantly better
        if score_spread > 0.1:
            top_score = min(1.0, top_score * 1.1)
    
    # Further lowered thresholds for FAQ/PDF content
    # FAQ documents often have lower TF-IDF scores due to question format
    if top_score >= 0.08:  # Further lowered
        label = "high"
    elif top_score >= 0.02:  # Further lowered
        label = "medium"
    else:
        label = "low"
    
    return top_score, label

def should_escalate(label: str, threshold_label: str = "medium") -> bool:
    order = {"low":0, "medium":1, "high":2}
    return order.get(label,0) < order.get(threshold_label,1)

# ------------------------------
# Escalation POST
# ------------------------------
def post_escalation(endpoint: str, payload: Dict[str,Any], headers: Dict[str,str]=None, timeout:int=6):
    try:
        resp = requests.post(endpoint, json=payload, headers=headers or {}, timeout=timeout)
        try:
            return True, resp.json()
        except Exception:
            return True, {"raw_response": resp.text}
    except Exception as e:
        return False, {"error": str(e)}

# ------------------------------
# CLI chat loop
# ------------------------------
def run_cli(doc_path: str, escalation_url: str, escalation_headers: Dict[str,str], threshold_label: str):
    raw = load_document(doc_path)
    chunks = chunk_document(raw)
    retriever = TfIdfRetriever(chunks)

    print(f"Loaded document '{doc_path}' with {len(chunks)} chunks.")
    print("Type questions (enter blank line to quit).")

    while True:
        try:
            user_q = input("\nUser question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if user_q == "":
            print("Empty input — exiting.")
            break

        # Retrieve (increased to 5 for better context)
        retrieved = retriever.retrieve(user_q, top_k=5)
        
        # Debug: Show top retrieval scores
        if retrieved:
            print(f"\n[Debug] Top retrieval scores:")
            for i, r in enumerate(retrieved[:3], 1):
                print(f"  {i}. Score: {r['score']:.4f} | Section: {r['section_title'][:50]}")

        # Build prompt (for inspection)
        prompt = build_prompt(retrieved, user_q)

        # Generate answer (fallback deterministic)
        answer = generate_answer_from_snippets(retrieved, user_q)

        # Confidence
        score, label = compute_confidence(retrieved)

        # Decide escalation
        escalate = should_escalate(label, threshold_label)

        escalation_request_id = None
        if escalate:
            payload = {
                "user_question": user_q,
                "retrieved_snippets": [
                    {"section_title": r["section_title"], "content": r["content"], "score": r["score"]}
                    for r in retrieved
                ],
                "model_attempted_answer": answer,
                "confidence_score": score,
                "confidence_label": label
            }
            print(f"\n[Escalating] confidence_label={label} score={score:.4f}")
            ok, resp = post_escalation(escalation_url, payload, headers=escalation_headers)
            if ok:
                # Attempt to extract id if present
                if isinstance(resp, dict) and resp.get("id"):
                    escalation_request_id = resp.get("id")
                else:
                    escalation_request_id = str(uuid.uuid4())
                print("[Escalation succeeded]", resp)
            else:
                print("[Escalation failed]", resp)

        # Prepare structured output
        source_reference = [
            {"section_title": r["section_title"], "score": r["score"], "snippet_preview": r["content"][:300]}
            for r in retrieved
        ]
        output = {
            "answer_text": answer,
            "confidence": {"score": score, "label": label},
            "source_reference": source_reference,
            "escalated_to_human": bool(escalate),
            "escalation_request_id": escalation_request_id
        }

        print("\n[Response JSON]")
        print(json.dumps(output, indent=2, ensure_ascii=False))
        print("\n[Answer shown to user]\n")
        print(answer)

# ------------------------------
# CLI helper
# ------------------------------
def parse_headers(header_list: List[str]) -> Dict[str,str]:
    headers = {}
    for h in header_list or []:
        if ':' in h:
            k,v = h.split(':',1)
            headers[k.strip()] = v.strip()
    return headers

def main():
    parser = argparse.ArgumentParser(description="FAQ Support Bot - Single Product (CLI)")
    parser.add_argument("--doc", required=True, help="Path to FAQ/docs file (PDF, md, or txt).")
    parser.add_argument("--escalation_url", required=True, help="Escalation POST endpoint URL.")
    parser.add_argument("--escalation_header", action="append", default=[], help="Optional header e.g. 'Authorization: Bearer ...'")
    parser.add_argument("--threshold", choices=["low","medium","high"], default="medium", help="Confidence threshold label for escalation.")
    args = parser.parse_args()

    if not os.path.exists(args.doc):
        print(f"Error: Document not found: {args.doc}", file=sys.stderr)
        sys.exit(1)
    
    headers = parse_headers(args.escalation_header)
    run_cli(args.doc, args.escalation_url, headers, args.threshold)

if __name__ == "__main__":
    main()
