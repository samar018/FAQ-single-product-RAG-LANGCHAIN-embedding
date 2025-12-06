#!/usr/bin/env python3
"""
Helper script to extract text from PDF to a text file for use with the FAQ bot.
"""
import sys
import os

def extract_pdf_text(pdf_path: str, output_path: str = None):
    """Extract text from PDF file"""
    if output_path is None:
        output_path = pdf_path.replace('.pdf', '.txt')
    
    try:
        # Try PyPDF2 first
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = '\n'.join([page.extract_text() for page in reader.pages])
        except ImportError:
            # Try pdfplumber as alternative
            try:
                import pdfplumber
                text = ""
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        text += page.extract_text() + "\n"
            except ImportError:
                print("Error: Need either PyPDF2 or pdfplumber installed.")
                print("Install one with: pip install PyPDF2")
                print("Or: pip install pdfplumber")
                sys.exit(1)
        
        # Write to output file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        print(f"✓ Successfully extracted text from '{pdf_path}'")
        print(f"✓ Saved to '{output_path}'")
        print(f"✓ Total characters: {len(text)}")
        return output_path
        
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_pdf_to_text.py <pdf_file> [output_file]")
        print("\nExample:")
        print("  python extract_pdf_to_text.py 'FinAI Comprehensive FAQ.pdf'")
        print("  python extract_pdf_to_text.py 'FinAI Comprehensive FAQ.pdf' faq.txt")
        sys.exit(1)
    
    pdf_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(pdf_file):
        print(f"Error: PDF file not found: {pdf_file}")
        sys.exit(1)
    
    extract_pdf_text(pdf_file, output_file)

