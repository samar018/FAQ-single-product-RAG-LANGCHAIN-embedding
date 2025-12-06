from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route("/", methods=["GET"])
def root():
    """Root endpoint for testing"""
    return jsonify({
        "message": "Escalation Server is running",
        "endpoints": {
            "/escalate": "POST - Submit escalation request"
        }
    }), 200

@app.route("/escalate", methods=["GET", "POST"])
def escalate():
    """Handle escalation requests"""
    if request.method == "GET":
        # Helpful message for GET requests
        return jsonify({
            "message": "This endpoint only accepts POST requests",
            "example": {
                "method": "POST",
                "url": "/escalate",
                "body": {
                    "user_question": "Your question here"
                }
            }
        }), 200
    
    # Handle POST requests
    try:
        data = request.get_json() or {}
        response = {
            "id": str(uuid.uuid4()),
            "status": "queued_for_human_review",
            "received_question": data.get("user_question")
        }
        print("Escalation received:", data)
        return jsonify(response), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
