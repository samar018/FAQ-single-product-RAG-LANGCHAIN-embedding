# How to Use the FAQ Bot System

## Step-by-Step Instructions

### 1. Activate Virtual Environment

First, activate your virtual environment:

**Windows PowerShell:**
```powershell
.\venv\Scripts\Activate.ps1
```

**Windows CMD:**
```cmd
.\venv\Scripts\activate.bat
```

### 2. Install Dependencies (if not already installed)

```powershell
pip install -r requirements.txt
```

### 3. Start the Escalation Server

Open a **new terminal window** and run:

```powershell
python dummy_escalation_server.py
```

You should see:
```
 * Running on http://0.0.0.0:5000
```

**Keep this terminal open** - the server needs to keep running.

### 4. Prepare Your FAQ Document

The FAQ bot needs a text or markdown file. You have a PDF file (`FinAI Comprehensive FAQ.pdf`).

**Option A: Convert PDF to Text** (if you have PyPDF2 or similar)
```powershell
# You may need to install: pip install PyPDF2
python -c "import PyPDF2; pdf = open('FinAI Comprehensive FAQ.pdf', 'rb'); reader = PyPDF2.PdfReader(pdf); text = '\n'.join([page.extract_text() for page in reader.pages]); open('faq.txt', 'w', encoding='utf-8').write(text)"
```

**Option B: Create a Simple Test FAQ File**

Create a file named `faq.txt` or `faq.md` with your FAQ content in plain text or markdown format.

### 5. Run the FAQ Bot CLI

In a **new terminal window** (keep the server running in the first one), run:

```powershell
python faq_bot_CLI.py --doc faq.txt --escalation_url http://localhost:5000/escalate
```

**Or with a markdown file:**
```powershell
python faq_bot_CLI.py --doc faq.md --escalation_url http://localhost:5000/escalate
```

**Optional parameters:**
- `--threshold [low|medium|high]` - Change confidence threshold (default: medium)
  - `low`: Only escalates when confidence is very low
  - `medium`: Escalates when confidence is low or medium
  - `high`: Escalates more frequently

**Example with threshold:**
```powershell
python faq_bot_CLI.py --doc faq.txt --escalation_url http://localhost:5000/escalate --threshold high
```

### 6. Interact with the Bot

Once the bot starts, you'll see:
```
Loaded document 'faq.txt' with X chunks.
Type questions (enter blank line to quit).

User question: 
```

**Type your question** and press Enter. The bot will:
1. Search the FAQ document
2. Generate an answer
3. Show confidence score
4. Escalate to human if confidence is too low
5. Display the response

**Example questions:**
- "What is FinAI?"
- "How do I create an account?"
- "What are the pricing plans?"

**To exit:** Press Enter on an empty line or Ctrl+C

## Quick Start Example

```powershell
# Terminal 1: Start server
python dummy_escalation_server.py

# Terminal 2: Run bot (in a new terminal)
python faq_bot_CLI.py --doc faq.txt --escalation_url http://localhost:5000/escalate
```

## Troubleshooting

- **"Method Not Allowed"**: Make sure the escalation server is running
- **"Document not found"**: Check the file path is correct
- **Import errors**: Make sure you activated the virtual environment and installed requirements

