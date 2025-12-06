# How to Run the FAQ Bot with RAG

## Prerequisites

1. **Activate Virtual Environment**
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

2. **Install/Update Dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

## Option 1: Run with Web Frontend (Recommended)

### Step 1: Start Escalation Server (Terminal 1)
```powershell
.\venv\Scripts\Activate.ps1
python dummy_escalation_server.py
```
Keep this running. It will show: `* Running on http://0.0.0.0:5000`

### Step 2: Start FAQ Bot API Server (Terminal 2)
```powershell
.\venv\Scripts\Activate.ps1
python faq_bot_api.py --doc "FinAI Comprehensive FAQ.pdf" --escalation_url http://localhost:5000/escalate --use_llm
```

**Options:**
- `--doc` - Path to your PDF file (required)
- `--escalation_url` - Escalation endpoint (default: http://localhost:5000/escalate)
- `--threshold` - Confidence threshold 0.0-1.0 (default: 0.55)
- `--use_llm` - Use OpenAI/LLM for answer generation (optional, will use fallback if not set)
- `--port` - Port for API server (default: 8000)
- `--host` - Host to bind to (default: 0.0.0.0)

### Step 3: Open Web Interface
Open your browser and go to:
```
http://localhost:8000
```

You can now:
- Ask questions through the web interface
- See answers with confidence scores
- View source references

## Option 2: Run CLI Version

### Single Command
```powershell
.\venv\Scripts\Activate.ps1
python faq_bot_rag.py --doc "FinAI Comprehensive FAQ.pdf" --escalation_url http://localhost:5000/escalate --use_llm
```

**Options:**
- `--doc` - Path to your PDF file (required)
- `--escalation_url` - Escalation endpoint (default: http://localhost:5000/escalate)
- `--threshold` - Confidence threshold 0.0-1.0 (default: 0.55)
- `--use_llm` - Use OpenAI/LLM for answer generation

### Interactive Mode
After running, you'll see:
```
Loading PDF and extracting FAQs...
✓ Extracted X FAQ pairs
Building vector store...
✓ Vector store built

FAQ Bot ready! Type your questions (blank line to quit):

Question: 
```

Type your questions and press Enter to get answers.

## Option 3: Initialize via Web Interface

If you don't provide `--doc` when starting the API server:

1. Start the API server:
   ```powershell
   python faq_bot_api.py
   ```

2. Open http://localhost:8000

3. Use the initialization form to:
   - Enter document path
   - Set escalation URL
   - Set confidence threshold
   - Enable/disable LLM

4. Click "Initialize Document"

5. Start asking questions!

## Environment Variables (Optional)

### For OpenAI/GitHub Models:
```powershell
# For GitHub AI models
$env:GITHUB_TOKEN = "your_github_token"

# OR for standard OpenAI
$env:OPENAI_API_KEY = "your_openai_key"
```

**Note:** The system will work without these - it will use fallback answer extraction from the FAQ pairs.

## Example Usage

### Example 1: Basic Run (No LLM)
```powershell
python faq_bot_api.py --doc "FinAI Comprehensive FAQ.pdf"
```

### Example 2: With LLM
```powershell
python faq_bot_api.py --doc "FinAI Comprehensive FAQ.pdf" --use_llm
```

### Example 3: Custom Threshold
```powershell
python faq_bot_api.py --doc "FinAI Comprehensive FAQ.pdf" --threshold 0.6
```

### Example 4: Custom Port
```powershell
python faq_bot_api.py --doc "FinAI Comprehensive FAQ.pdf" --port 8080
```

## Troubleshooting

### Error: "No FAQ pairs found"
- Check your PDF format - it should have Q1, Q2, etc. or numbered Q&A format
- The system looks for patterns like:
  - `Q1 What is FinAI?`
  - `1. Question? Answer`

### Error: "Module not found"
- Make sure virtual environment is activated
- Run: `pip install -r requirements.txt`

### Error: "OpenAI API error"
- Set `OPENAI_API_KEY` or `GITHUB_TOKEN` environment variable
- Or run without `--use_llm` flag (will use fallback)

### Low Confidence Scores
- Try lowering the threshold: `--threshold 0.4`
- Check if your questions match the FAQ format in the PDF

## Quick Start (All-in-One)

```powershell
# Terminal 1: Escalation Server
.\venv\Scripts\Activate.ps1
python dummy_escalation_server.py

# Terminal 2: FAQ Bot API
.\venv\Scripts\Activate.ps1
python faq_bot_api.py --doc "FinAI Comprehensive FAQ.pdf" --escalation_url http://localhost:5000/escalate

# Then open: http://localhost:8000
```

