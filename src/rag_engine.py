"""
RAG Query Engine for Safwa Bank Policy Chatbot.

Flow:
  1. Embed user question with sentence-transformer
  2. Retrieve top-K chunks from ChromaDB
  3. Detect query language (Arabic / English)
  4. Build role-aware system prompt in the detected language
  5. Call local Ollama LLM (Mistral 7B) with retrieved context + chat history
  6. Return { answer, sources, role_used }

NOTE: All processing happens locally — no data leaves the machine.
"""

import re
import sys
import json
import requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    OLLAMA_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS,
    EMBEDDING_MODEL, COLLECTION_NAME, CHROMA_DIR, TOP_K_RESULTS, ROLES
)

_embed_model  = None
_chroma_coll  = None

def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embed_model

def _get_collection():
    global _chroma_coll
    if _chroma_coll is None:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _chroma_coll = client.get_collection(COLLECTION_NAME)
    return _chroma_coll

def collection_ready() -> bool:
    """Return True if ChromaDB collection exists and has documents."""
    try:
        coll = _get_collection()
        return coll.count() > 0
    except Exception:
        return False


def llm_ready() -> bool:
    """Return True if the local Ollama LLM server is reachable and model is loaded."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code != 200:
            return False
        models = resp.json().get("models", [])
        return any(m.get("name", "").startswith(LLM_MODEL) for m in models)
    except Exception:
        return False


_ARABIC_RANGE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')

def _detect_language(text: str) -> str:
    """Detect if the text is primarily Arabic or English."""
    arabic_chars = len(_ARABIC_RANGE.findall(text))
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha == 0:
        return "ar"  
    return "ar" if arabic_chars / total_alpha > 0.3 else "en"


def _call_local_llm(prompt: str, system: str = "") -> str:
    """
    Call the local Ollama LLM and return the generated text.
    All data stays on localhost — nothing leaves the machine.
    """
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": LLM_TEMPERATURE,
            "num_predict": LLM_MAX_TOKENS,
        },
    }

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            "تعذر الاتصال بخادم Ollama. تأكد من أنه قيد التشغيل.\n"
            "Cannot connect to Ollama. Run: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise TimeoutError(
            "انتهت مهلة الاتصال بنموذج الذكاء الاصطناعي المحلي.\n"
            "Local LLM request timed out."
        )
    except Exception as e:
        raise RuntimeError(f"LLM Error: {e}")


def _stream_local_llm(prompt: str, system: str = ""):
    """
    Stream tokens from the local Ollama LLM.
    Yields individual response chunks as they are generated.
    """
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": True,
        "options": {
            "temperature": LLM_TEMPERATURE,
            "num_predict": LLM_MAX_TOKENS,
        },
    }

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=300,
            stream=True,
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                data = json.loads(line)
                token = data.get("response", "")
                if token:
                    yield token
                if data.get("done", False):
                    break
    except Exception as e:
        yield f"\n\n خطأ: {e}"


ROLE_STYLES_AR = {
    "it": "المستخدم موظف **تقنية معلومات**. استخدم المصطلحات التقنية بحرية. قدّم خطوات تقنية دقيقة وأشر إلى البروتوكولات والضوابط الأمنية.",
    "business": "المستخدم موظف **أعمال**. ركّز على الأثر التجاري والتزامات الامتثال وسير العمل التشغيلي. تجنّب المصطلحات التقنية المعمّقة.",
    "management": "المستخدم **مدير / تنفيذي**. قدّم توجيهات استراتيجية عالية المستوى ومتطلبات الحوكمة وسلاسل المساءلة والآثار المترتبة على المخاطر.",
    "hr": "المستخدم موظف **موارد بشرية**. ركّز على السياسات المتعلقة بحقوق الموظفين والتدريب والإجراءات التأديبية ومتطلبات الامتثال.",
    "legal": "المستخدم في **القانوني / الامتثال**. استخدم لغة قانونية وتنظيمية دقيقة. أشر إلى مواد وبنود محددة من الوثائق.",
    "general": "المستخدم **موظف عام**. استخدم أبسط لغة ممكنة. تجنّب كل المصطلحات التقنية والقانونية. اشرح بلغة يومية واضحة.",
}

ROLE_STYLES_EN = {
    "it": "The user is an IT/Technical employee. Use technical terminology. Provide precise technical steps and reference security controls.",
    "business": "The user is a Business employee. Focus on business impact, compliance, and workflows. Avoid deep technical jargon.",
    "management": "The user is a Manager/Executive. Provide high-level strategic guidance, governance requirements, and risk implications.",
    "hr": "The user is an HR employee. Focus on employee rights, training obligations, and compliance requirements for HR.",
    "legal": "The user is in Legal/Compliance. Use precise legal language. Reference specific articles and clauses from the documents.",
    "general": "The user is General Staff. Use the simplest language possible. Explain in everyday terms with numbered steps.",
}


def build_system_prompt(user_name: str, role: str, context: str, history_text: str, lang: str = "ar") -> str:
    role_label_ar = ROLES.get(role, {}).get("ar", "موظف عام")
    role_label_en = ROLES.get(role, {}).get("en", "General Staff")

    if lang == "ar":
        role_style = ROLE_STYLES_AR.get(role, ROLE_STYLES_AR["general"])
        return f"""أنت "مساعد صفوة" — المساعد الذكي الرسمي لبنك الصفوة الإسلامي لسياسات الأمن السيبراني وحماية البيانات.

الاسم: {user_name}
الدور: {role_label_ar}
{role_style}

═══ القواعد الصارمة ═══
1. أجب فقط بناءً على مقتطفات الوثائق أدناه. لا تستخدم معلومات خارجية لأسئلة السياسات.
2. استثناء: إذا كان المستخدم يلقي التحية (مثل "مرحبا"، "السلام عليكم")، قم بالرد بتحية مهنية وودية تتضمن اسمه (مثال: "أهلاً بك يا {user_name}، كيف يمكنني مساعدتك اليوم؟") دون البحث في الوثائق.
3. إذا لم تجد الإجابة على سؤاله في المقتطفات، قل: "لا تتوفر لديّ معلومات كافية في الوثائق المتاحة للإجابة على هذا السؤال."
4. إذا طُلبت خطوات، قدّمها مرقّمة بوضوح.
5. كُن موجزاً ومهنياً ودقيقاً.
6. لا تختلق أرقام مواد أو صفحات أو اقتباسات.
7.  يجب أن تكون إجابتك بالكامل باللغة العربية. لا تكتب بالإنجليزية أبداً.

═══ سجل المحادثة ═══
{history_text if history_text else "لا توجد رسائل سابقة."}

═══ مقتطفات الوثائق ═══
{context}
═══════════════════════

أجب الآن على سؤال المستخدم بناءً على المقتطفات أعلاه فقط. أجب باللغة العربية."""
    else:
        role_style = ROLE_STYLES_EN.get(role, ROLE_STYLES_EN["general"])
        return f"""You are "Safwa Assistant" — the official AI Policy Assistant of Safwa Islamic Bank for cybersecurity and data protection policies.

User: {user_name}
Role: {role_label_en}
{role_style}

═══ STRICT RULES ═══
1. Answer ONLY from the document excerpts below. Do NOT use outside knowledge for policy questions.
2. EXCEPTION: If the user provides a basic greeting (e.g., "Hello", "Hi"), reply with a polite and professional greeting using their name (e.g., "Hello {user_name}, how can I assist you today?") without requiring document excerpts.
3. If the answer is NOT in the excerpts, say: "I don't have sufficient information in the available documents to answer this accurately."
4. If asked for steps, provide clearly numbered steps.
5. Be concise, professional, and precise.
6. Do NOT fabricate article numbers, page numbers, or quotes.
7. You MUST answer entirely in English.

═══ CONVERSATION HISTORY ═══
{history_text if history_text else "No previous messages."}

═══ DOCUMENT EXCERPTS ═══
{context}
═════════════════════════

Answer the user's question based strictly on the excerpts above. Answer in English."""



def _check_basic_greeting(question: str, user_name: str, role: str) -> dict | None:
    """
    Check if the user's question is a simple greeting.
    If so, return a fast predefined response instantly to bypass the full RAG pipeline.
    """
    clean_msg = re.sub(r'[^\w\s]', '', question).strip().lower()
    if not clean_msg:
        return None
        
    greetings = {
        "مرحبا", "مرحباً", "السلام عليكم", "هلا", "اهلين", "أهلا", "اهلا", 
        "صباح الخير", "مساء الخير", "يعطيك العافية", "hi", "hello", "hey"
    }
    
    words = clean_msg.split()
    if clean_msg in greetings or (len(words) <= 3 and any(clean_msg.startswith(g) for g in greetings)):
        return {
            "answer": f"أهلاً {user_name}، كيف يمكنني مساعدتك اليوم؟",
            "sources": [],
            "role_used": role
        }
    return None



def _build_rag_context(question: str, role: str, user_name: str, chat_history: list = None):
    """
    Shared logic: embed question, retrieve chunks, build prompt.
    Returns (system_prompt, question, sources, role) or error dict.
    """
    lang = _detect_language(question)

    embed_model = _get_embed_model()
    q_embedding = embed_model.encode([question], normalize_embeddings=True)[0].tolist()

    try:
        collection = _get_collection()
        results = collection.query(
            query_embeddings=[q_embedding],
            n_results=TOP_K_RESULTS,
            include=["documents", "metadatas", "distances"],
        )
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]
    except Exception as e:
        return {
            "error": True,
            "answer": f"لم يتم تهيئة قاعدة المعرفة بعد.\nKnowledge base not ready.\n\nError: {e}",
            "sources": [],
            "role_used": role,
        }

    context_parts = []
    sources = []
    seen_sources = set()

    for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
        relevance = round((1 - float(dist)) * 100, 1)
        context_parts.append(
            f"[مقطع {i+1}]\n"
            f"الملف: {meta['source_file']}\n"
            f"الصفحة: {meta['page_number']}\n"
            f"القسم: {meta['section_title']}\n"
            f"---\n{doc}"
        )
        src_key = (meta["source_file"], meta.get("section_title", ""))
        if src_key not in seen_sources:
            seen_sources.add(src_key)
            sources.append({
                "file":      meta["source_file"],
                "page":      meta.get("page_number", "—"),
                "section":   meta.get("section_title", "—"),
                "relevance": relevance,
            })

    context = "\n\n".join(context_parts)

    history_text = ""
    if chat_history:
        for msg in (chat_history or [])[-4:]:
            label = "المستخدم" if msg["role"] == "user" else "مساعد صفوة"
            history_text += f"{label}: {msg['content'][:200]}\n\n"

    system_prompt = build_system_prompt(user_name, role, context, history_text, lang)

    return {
        "error": False,
        "system_prompt": system_prompt,
        "sources": sources[:4],
        "role_used": role,
        "lang": lang,
    }


def query_rag(question: str, role: str, user_name: str, chat_history: list = None) -> dict:
    """
    Execute a full RAG query using the local Ollama LLM (non-streaming).
    """
    greeting_resp = _check_basic_greeting(question, user_name, role)
    if greeting_resp:
        return greeting_resp

    ctx = _build_rag_context(question, role, user_name, chat_history)
    if ctx.get("error"):
        return {"answer": ctx["answer"], "sources": ctx["sources"], "role_used": ctx["role_used"]}

    try:
        answer = _call_local_llm(prompt=question, system=ctx["system_prompt"])
    except Exception as e:
        answer = f"عذراً، حدث خطأ أثناء الاتصال بنموذج الذكاء الاصطناعي المحلي.\nError: {e}"

    return {
        "answer":    answer,
        "sources":   ctx["sources"],
        "role_used": ctx["role_used"],
    }


def query_rag_stream(question: str, role: str, user_name: str, chat_history: list = None):
    """
    Execute a RAG query with streaming response.
    Yields dicts: first {"sources": [...], "role_used": str}, then {"token": str} for each token.
    """
    greeting_resp = _check_basic_greeting(question, user_name, role)
    if greeting_resp:
        yield {"sources": greeting_resp["sources"], "role_used": greeting_resp["role_used"]}
        yield {"token": greeting_resp["answer"]}
        yield {"done": True}
        return

    ctx = _build_rag_context(question, role, user_name, chat_history)
    if ctx.get("error"):
        yield {"sources": ctx["sources"], "role_used": ctx["role_used"]}
        yield {"token": ctx["answer"]}
        yield {"done": True}
        return

    yield {"sources": ctx["sources"], "role_used": ctx["role_used"]}

    try:
        for token in _stream_local_llm(prompt=question, system=ctx["system_prompt"]):
            yield {"token": token}
    except Exception as e:
        yield {"token": f"\n\n⚠️ خطأ: {e}"}

    yield {"done": True}