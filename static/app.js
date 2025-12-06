// API base URL
const API_BASE = '';

// State
let isInitialized = false;

// DOM Elements
const initPanel = document.getElementById('initPanel');
const chatPanel = document.getElementById('chatPanel');
const initBtn = document.getElementById('initBtn');
const resetBtn = document.getElementById('resetBtn');
const docPathInput = document.getElementById('docPath');
const escalationUrlInput = document.getElementById('escalationUrl');
const thresholdSelect = document.getElementById('threshold');
const questionInput = document.getElementById('questionInput');
const sendBtn = document.getElementById('sendBtn');
const chatMessages = document.getElementById('chatMessages');
const loadingIndicator = document.getElementById('loadingIndicator');
const initStatus = document.getElementById('initStatus');
const statusText = document.getElementById('statusText');

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    setupEventListeners();
});

// Check if server is healthy and document is already loaded
async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE}/api/health`);
        const data = await response.json();
        
        if (data.document_loaded) {
            isInitialized = true;
            showChatPanel();
            updateStatus('Document already loaded');
        }
    } catch (error) {
        console.error('Health check failed:', error);
        updateStatus('Server connection error');
    }
}

// Setup event listeners
function setupEventListeners() {
    initBtn.addEventListener('click', initializeDocument);
    resetBtn.addEventListener('click', reset);
    sendBtn.addEventListener('click', sendQuestion);
    questionInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendQuestion();
        }
    });
}

// Initialize document
async function initializeDocument() {
    const docPath = docPathInput.value.trim();
    const escalationUrl = escalationUrlInput.value.trim();
    const threshold = thresholdSelect.value;

    if (!docPath) {
        showStatus(initStatus, 'Please enter a document path', 'error');
        return;
    }

    initBtn.disabled = true;
    initBtn.textContent = 'Initializing...';
    showStatus(initStatus, 'Loading document...', 'success');

    try {
        const response = await fetch(`${API_BASE}/api/initialize`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                doc_path: docPath,
                escalation_url: escalationUrl,
                threshold: threshold
            })
        });

        const data = await response.json();

        if (response.ok) {
            isInitialized = true;
            showChatPanel();
            const count = data.faq_pairs || data.chunks || 0;
            showStatus(initStatus, `✓ Document loaded: ${count} FAQ pairs`, 'success');
            updateStatus(`Document loaded: ${count} FAQ pairs`);
        } else {
            showStatus(initStatus, `Error: ${data.error}`, 'error');
            updateStatus('Initialization failed');
        }
    } catch (error) {
        showStatus(initStatus, `Error: ${error.message}`, 'error');
        updateStatus('Connection error');
    } finally {
        initBtn.disabled = false;
        initBtn.textContent = 'Initialize Document';
    }
}

// Send question
async function sendQuestion() {
    const question = questionInput.value.trim();

    if (!question) {
        return;
    }

    if (!isInitialized) {
        alert('Please initialize the document first');
        return;
    }

    // Add user message to chat
    addMessage('user', question);
    questionInput.value = '';
    sendBtn.disabled = true;
    loadingIndicator.style.display = 'block';
    updateStatus('Processing question...');

    try {
        const response = await fetch(`${API_BASE}/api/ask`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question: question
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Add bot response
            addBotMessage(data);
            updateStatus('Ready');
        } else {
            addMessage('bot', `Error: ${data.error}`, null, true);
            updateStatus('Error occurred');
        }
    } catch (error) {
        addMessage('bot', `Connection error: ${error.message}`, null, true);
        updateStatus('Connection error');
    } finally {
        sendBtn.disabled = false;
        loadingIndicator.style.display = 'none';
        questionInput.focus();
    }
}

// Add message to chat
function addMessage(type, text, metadata = null, isError = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = text;
    messageDiv.appendChild(bubble);

    if (metadata) {
        const metaDiv = document.createElement('div');
        metaDiv.className = 'message-meta';
        
        if (metadata.confidence) {
            const confidenceBadge = document.createElement('span');
            confidenceBadge.className = `confidence-badge ${metadata.confidence.label}`;
            confidenceBadge.textContent = `Confidence: ${metadata.confidence.label} (${(metadata.confidence.score * 100).toFixed(1)}%)`;
            metaDiv.appendChild(confidenceBadge);
        }
        
        messageDiv.appendChild(metaDiv);
    }

    if (isError) {
        bubble.style.background = '#f8d7da';
        bubble.style.color = '#721c24';
    }

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add bot message with full details
function addBotMessage(data) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = `<div>${escapeHtml(data.answer_text)}</div>`;
    messageDiv.appendChild(bubble);

    // Confidence badge
    const metaDiv = document.createElement('div');
    metaDiv.className = 'message-meta';
    
    const confidenceBadge = document.createElement('span');
    confidenceBadge.className = `confidence-badge ${data.confidence.label}`;
    confidenceBadge.textContent = `Confidence: ${data.confidence.label} (${(data.confidence.score * 100).toFixed(1)}%)`;
    metaDiv.appendChild(confidenceBadge);
    
    messageDiv.appendChild(metaDiv);

    // Escalation notice
    if (data.escalated_to_human) {
        const escalationDiv = document.createElement('div');
        escalationDiv.className = 'escalation-notice';
        escalationDiv.innerHTML = `⚠️ This question has been escalated to human support. Request ID: ${data.escalation_request_id || 'N/A'}`;
        messageDiv.appendChild(escalationDiv);
    }

    // Source reference (simplified - now just a string)
    if (data.source_reference && typeof data.source_reference === 'string' && data.source_reference.trim()) {
        const sourceDiv = document.createElement('div');
        sourceDiv.className = 'source-reference';
        sourceDiv.innerHTML = `
            <h4>Source:</h4>
            <div class="source-item">
                ${escapeHtml(data.source_reference)}
            </div>
        `;
        messageDiv.appendChild(sourceDiv);
    }

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Show chat panel
function showChatPanel() {
    initPanel.style.display = 'none';
    chatPanel.style.display = 'block';
    questionInput.focus();
}

// Reset
function reset() {
    if (confirm('Are you sure you want to reset? This will clear the chat and require re-initialization.')) {
        isInitialized = false;
        chatPanel.style.display = 'none';
        initPanel.style.display = 'block';
        chatMessages.innerHTML = '';
        updateStatus('Ready');
    }
}

// Show status message
function showStatus(element, message, type) {
    element.textContent = message;
    element.className = `status-message ${type}`;
}

// Update status bar
function updateStatus(text) {
    statusText.textContent = text;
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

