#  Safwa Bank AI Policy Chatbot

A **fully local, offline RAG-powered chatbot** for Safwa Bank employees, providing accurate, role-aware answers to questions about bank policies and cybersecurity regulations with full source citations.

> Data Security: All processing happens 100% locally on the machine. No data is sent to any external API or cloud service. This complies with Safwa Bank's strict data sovereignty requirements.

---

https://raneemsadeh.github.io/safwa-ai-assistant/

##  Features

| Feature | Description |
|---|---|
|  **28 Policy Documents** | Ingests all Arabic regulation & policy .docx files |
|  **Role-Aware Answers** | Adapts language for IT, Business, Management, HR, Legal, or General Staff |
|  **Source Citations** | Every answer cites document name, estimated page & section |
|  **Document-Only Answers** | Never hallucinate — refuses to answer outside the documents |
|  **100% Offline** | All AI models run locally — no data leaves the machine |
|  **Employee Accounts** | Login by Employee ID; profile drives response style |
|  **Conversation History** | Full conversation history stored locally in SQLite |
|  **Bilingual** | Arabic + English interface, responds in query language |
|  **Admin Ingestion Panel** | Re-ingest documents anytime via `Ctrl+Shift+A` |

---

##  Setup & Installation

### 1. Install Ollama (Local LLM Server)

Download and install Ollama from [ollama.com](https://ollama.com) or via winget:

```powershell
winget install Ollama.Ollama
```

### 2. Download the Mistral 7B Model (One-Time)

```powershell
ollama pull mistral
```

> **Note:** This downloads ~4.4 GB. After this, the system works **100% offline**.

### 3. Install Python Dependencies

```powershell
pip install -r requirements.txt
```

> **Note:** First run will also download the `paraphrase-multilingual-mpnet-base-v2` embedding model (~420 MB).

### 4. Ingest Policy Documents (One-Time Setup)

```powershell
python src/ingest.py
```

This processes all 28 `.docx` files in `Data/`, chunks them, embeds them, and stores in local ChromaDB. Takes ~5-10 minutes on first run.

### 5. Start the Application

Make sure Ollama is running (it starts automatically on Windows), then:

```powershell
python app.py
```

Open your browser at: **http://localhost:5000**

---

##  First Use

1. **Register**: Enter your name, Employee ID, department, and role
2. **Start chatting**: Ask any question about Safwa Bank policies
3. **Get cited answers**: Every response includes document references

### Example Questions
- `ما هي الإجراءات الواجب اتباعها عند إرسال بيانات إلى جهة خارجية؟`
- `What are the requirements for reporting a data breach?`
- `كيف أُجري تقييم أثر حماية البيانات (DPIA)؟`
- `I want to share customer data with a third party. What are the steps?`

---

##  Admin Panel

Access via **`Ctrl + Shift + A`** in the chat view.

- **Password**: `SafwaAdmin@2026` (change in `.env`)
- Use to re-ingest documents after updates
- Shows live ingestion progress and LLM status

---

##  Project Structure

```
RAG_System/
├── Data/                    ← 28 Arabic policy .docx files
├── chroma_db/               ← Auto-generated vector store (local)
├── safwa_users.db           ← SQLite user accounts & history
├── src/
│   ├── config.py            ← Central configuration
│   ├── database.py          ← User & conversation DB layer
│   ├── ingest.py            ← Document ingestion pipeline
│   └── rag_engine.py        ← RAG query + local Ollama LLM
├── templates/index.html     ← Premium bilingual SPA
├── static/css/style.css     ← Dark navy + gold design
├── static/js/app.js         ← Frontend application logic
├── app.py                   ← Flask web server
├── .env                     ← App secrets (keep private!)
└── requirements.txt         ← Python dependencies
```

---

##  Configuration (`.env`)

```env
SECRET_KEY=your_flask_secret      # Flask session secret
ADMIN_PASSWORD=your_admin_pass    # Admin panel password
```

Optional environment overrides (defaults work out of the box):

```env
OLLAMA_BASE_URL=http://localhost:11434   # Ollama server URL
LLM_MODEL=mistral                        # Model name in Ollama
```

---

##  Tech Stack

| Component | Technology |
|---|---|
| **LLM** | Mistral 7B via Ollama (100% local) |
| **Embeddings** | `paraphrase-multilingual-mpnet-base-v2` (local) |
| **Vector DB** | ChromaDB (local persistent) |
| **Backend** | Python + Flask |
| **Frontend** | Vanilla HTML/CSS/JS (glassmorphism design) |
| **User DB** | SQLite (built-in Python) |

---

##  Data Security Architecture

```
┌─────────────────────────────────────────────────┐
│                 LOCAL MACHINE                    │
│                                                 │
│  User ──→ Flask App ──→ RAG Engine              │
│                │              │                 │
│                │         ┌────┴────┐            │
│                │         │ ChromaDB │ (vectors) │
│                │         └─────────┘            │
│                │              │                 │
│                │     ┌────────┴────────┐        │
│                │     │  Ollama/Mistral  │ (LLM) │
│                │     └─────────────────┘        │
│                ▼                                │
│           Response                              │
│                                                 │
│      NO external API calls                    │
│      NO data leaves this machine              │
└─────────────────────────────────────────────────┘
```
## By Raneem Sadeh
