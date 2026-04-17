import sys
import os
import json
import threading
from pathlib import Path
from flask import (
    Flask, render_template, request, session,
    jsonify, redirect, url_for
)

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import SECRET_KEY, ADMIN_PASSWORD, ROLES, DEPARTMENTS
from database import (
    init_db, register_user, login_user, get_user,
    create_conversation, get_conversations,
    save_message, get_messages, get_recent_messages,
    update_conversation_title
)
from ingest import ingest_documents, get_ingest_status
from rag_engine import query_rag, collection_ready, llm_ready

app = Flask(__name__)
app.secret_key = SECRET_KEY


def current_user() -> dict | None:
    eid = session.get("employee_id")
    return get_user(eid) if eid else None

def require_auth():
    """Return (user, error_response). error_response is None if OK."""
    user = current_user()
    if not user:
        return None, jsonify({"error": "Not authenticated", "code": "AUTH_REQUIRED"}), 401
    return user, None, None


with app.app_context():
    init_db()


@app.route("/")
def index():
    user = current_user()
    return render_template("index.html", user=user, roles=ROLES, departments=DEPARTMENTS)



@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True)
    required = ["employee_id", "full_name", "department", "role"]
    for field in required:
        if not data.get(field, "").strip():
            return jsonify({"error": f"Field '{field}' is required."}), 400

    try:
        user = register_user(
            employee_id = data["employee_id"].strip().upper(),
            full_name   = data["full_name"].strip(),
            department  = data["department"].strip(),
            role        = data["role"].strip(),
            job_title   = data.get("job_title", "").strip(),
        )
        session["employee_id"] = user["employee_id"]
        return jsonify({"success": True, "user": _safe_user(user)})
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        return jsonify({"error": f"Registration failed: {e}"}), 500


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    eid = data.get("employee_id", "").strip().upper()
    if not eid:
        return jsonify({"error": "Employee ID is required."}), 400

    user = login_user(eid)
    if not user:
        return jsonify({"error": "Employee ID not found. Please register first."}), 404

    session["employee_id"] = user["employee_id"]
    return jsonify({"success": True, "user": _safe_user(user)})


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/auth/me", methods=["GET"])
def api_me():
    user = current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({"authenticated": True, "user": _safe_user(user)})


def _safe_user(user: dict) -> dict:
    """Strip sensitive fields before sending to client."""
    return {
        "employee_id": user["employee_id"],
        "full_name":   user["full_name"],
        "department":  user["department"],
        "role":        user["role"],
        "job_title":   user.get("job_title", ""),
        "last_login":  user.get("last_login"),
    }



@app.route("/api/conversations", methods=["GET"])
def api_conversations():
    user = current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    convs = get_conversations(user["employee_id"])
    return jsonify({"conversations": convs})


@app.route("/api/conversations/new", methods=["POST"])
def api_new_conversation():
    user = current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    conv_id = create_conversation(user["employee_id"])
    return jsonify({"conversation_id": conv_id})


@app.route("/api/conversations/<conv_id>/messages", methods=["GET"])
def api_get_messages(conv_id):
    user = current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    msgs = get_messages(conv_id)
    return jsonify({"messages": msgs})



@app.route("/api/chat", methods=["POST"])
def api_chat():
    user = current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json(force=True)
    message = data.get("message", "").strip()
    conv_id = data.get("conversation_id", "")

    if not message:
        return jsonify({"error": "Message is required."}), 400

    if not conv_id:
        conv_id = create_conversation(user["employee_id"])

    if not collection_ready():
        return jsonify({
            "error": "knowledge_base_not_ready",
            "message": "قاعدة المعرفة لم يتم تهيئتها بعد. يرجى تشغيل عملية الاستيعاب.\nKnowledge base not ready. Please run ingestion first.",
            "conversation_id": conv_id,
        }), 503

    save_message(conv_id, user["employee_id"], "user", message)

    recent = get_recent_messages(conv_id)
    user_msgs = [m for m in recent if m["role"] == "user"]
    if len(user_msgs) == 1:
        update_conversation_title(conv_id, message[:60])

    history = [m for m in recent if not (m["role"] == "user" and m["content"] == message)]

    # RAG
    result = query_rag(
        question     = message,
        role         = user["role"],
        user_name    = user["full_name"],
        chat_history = history,
    )

    save_message(
        conv_id,
        user["employee_id"],
        "assistant",
        result["answer"],
        sources=json.dumps(result["sources"], ensure_ascii=False),
    )

    return jsonify({
        "answer":          result["answer"],
        "sources":         result["sources"],
        "role_used":       result["role_used"],
        "conversation_id": conv_id,
    })


_ingest_thread = None
_ingest_lock   = threading.Lock()


@app.route("/api/admin/ingest", methods=["POST"])
def api_ingest():
    data = request.get_json(force=True)
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "Invalid admin password."}), 403

    global _ingest_thread
    with _ingest_lock:
        if _ingest_thread and _ingest_thread.is_alive():
            return jsonify({"error": "Ingestion already in progress."}), 409

        def run():
            try:
                ingest_documents()
            except Exception as e:
                print(f"Ingestion error: {e}")

        _ingest_thread = threading.Thread(target=run, daemon=True)
        _ingest_thread.start()

    return jsonify({"success": True, "message": "Ingestion started in background."})


@app.route("/api/admin/status", methods=["GET"])
def api_status():
    status = get_ingest_status()
    status["collection_ready"] = collection_ready()
    status["llm_ready"] = llm_ready()
    return jsonify(status)


if __name__ == "__main__":
    print("=" * 60)
    print("  [Bank] Safwa Bank Policy Chatbot")
    print("  [Web] http://localhost:5000")
    print("=" * 60)
    app.run(debug=False, host="0.0.0.0", port=5000)