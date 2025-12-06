# Frontend Usage Guide

## Quick Start

### 1. Start the Escalation Server (Terminal 1)

```powershell
.\venv\Scripts\Activate.ps1
python dummy_escalation_server.py
```

This runs on `http://localhost:5000`

### 2. Start the FAQ Bot API Server (Terminal 2)

**Option A: Auto-initialize with document**
```powershell
.\venv\Scripts\Activate.ps1
python faq_bot_api.py --doc "FinAI Comprehensive FAQ.pdf" --escalation_url http://localhost:5000/escalate
```

**Option B: Initialize via web interface**
```powershell
.\venv\Scripts\Activate.ps1
python faq_bot_api.py
```

Then use the web interface to initialize the document.

The API server runs on `http://localhost:8000` by default.

### 3. Open the Web Interface

Open your browser and go to:
```
http://localhost:8000
```

## Using the Web Interface

### Initialize Document

1. Enter the document path (e.g., `FinAI Comprehensive FAQ.pdf`)
2. Enter the escalation URL (default: `http://localhost:5000/escalate`)
3. Select confidence threshold (Low/Medium/High)
4. Click "Initialize Document"

### Ask Questions

1. Type your question in the input field
2. Press Enter or click "Send"
3. View the answer with:
   - Confidence score and label
   - Source references
   - Escalation status (if applicable)

### Features

- **Real-time chat interface** - Ask questions and get instant answers
- **Confidence indicators** - See how confident the bot is in its answer
- **Source references** - View the document sections used to generate the answer
- **Automatic escalation** - Low-confidence questions are automatically escalated
- **Modern UI** - Clean, responsive design

## API Endpoints

### `GET /api/health`
Check server status and document loading state.

### `POST /api/initialize`
Initialize the FAQ bot with a document.

**Request:**
```json
{
  "doc_path": "FinAI Comprehensive FAQ.pdf",
  "escalation_url": "http://localhost:5000/escalate",
  "threshold": "medium"
}
```

### `POST /api/ask`
Ask a question and get an answer.

**Request:**
```json
{
  "question": "What is FinAI?"
}
```

**Response:**
```json
{
  "answer_text": "...",
  "confidence": {
    "score": 0.85,
    "label": "high"
  },
  "source_reference": [...],
  "escalated_to_human": false
}
```

## Customization

### Change Port

```powershell
python faq_bot_api.py --port 8080
```

### Change Host

```powershell
python faq_bot_api.py --host 127.0.0.1
```

## Troubleshooting

- **"Document not initialized"**: Make sure you've initialized the document first
- **Connection errors**: Check that both servers are running (escalation server on port 5000, API server on port 8000)
- **Document not found**: Verify the document path is correct and the file exists

