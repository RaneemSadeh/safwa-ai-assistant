/**
 * Safwa Bank Policy Chatbot — Frontend Application
 *
 * Modules:
 *   API   — fetch wrappers for all backend endpoints
 *   App   — view management, auth state, initialization
 *   Chat  — conversation logic, message rendering, citations
 *   Admin — ingestion panel
 */

"use strict";

/* ══════════════════════════════════════════════════════════════════
   API MODULE
══════════════════════════════════════════════════════════════════ */
const API = {
  async post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  },

  async get(url) {
    const res = await fetch(url);
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  },

  async register(payload)      { return this.post("/api/auth/register", payload); },
  async login(employee_id)     { return this.post("/api/auth/login", { employee_id }); },
  async logout()               { return this.post("/api/auth/logout", {}); },
  async me()                   { return this.get("/api/auth/me"); },

  async newConversation()      { return this.post("/api/conversations/new", {}); },
  async getConversations()     { return this.get("/api/conversations"); },
  async getMessages(convId)    { return this.get(`/api/conversations/${convId}/messages`); },

  async chat(message, convId)  { return this.post("/api/chat", { message, conversation_id: convId }); },

  async adminStatus()          { return this.get("/api/admin/status"); },
  async triggerIngest(password){ return this.post("/api/admin/ingest", { password }); },
};


/* ══════════════════════════════════════════════════════════════════
   APP MODULE — view & auth management
══════════════════════════════════════════════════════════════════ */
const App = {
  currentUser: null,

  /** Initialize the application. Called on DOMContentLoaded. */
  init(serverUser) {
    this.currentUser = serverUser;

    if (serverUser) {
      this.enterChat(serverUser);
    } else {
      this.showView("login");
    }

    this._bindGlobalEvents();
  },

  showView(name) {
    ["login", "register", "chat"].forEach(v => {
      const el = document.getElementById(`view-${v}`);
      if (el) el.classList.toggle("hidden", v !== name);
    });
    // Re-render lucide icons after view switch
    setTimeout(() => lucide.createIcons(), 50);
  },

  enterChat(user) {
    this.currentUser = user;
    this.showView("chat");
    this._populateUserProfile(user);
    Chat.init();
    setTimeout(() => lucide.createIcons(), 100);
  },

  _populateUserProfile(user) {
    const nameEl  = document.getElementById("user-name-display");
    const roleEl  = document.getElementById("user-role-display");
    const deptEl  = document.getElementById("user-dept-display");
    const avatarEl = document.getElementById("user-avatar");
    const headerRole = document.getElementById("header-role");

    const roleMeta = {
      it:         { en: "IT / Technical",       ar: "تقنية المعلومات" },
      business:   { en: "Business",             ar: "الأعمال" },
      management: { en: "Management",           ar: "الإدارة" },
      hr:         { en: "HR",                   ar: "الموارد البشرية" },
      legal:      { en: "Legal / Compliance",   ar: "القانوني" },
      general:    { en: "General Staff",        ar: "موظف عام" },
    };
    const rm = roleMeta[user.role] || { en: user.role, ar: user.role };

    if (nameEl)  nameEl.textContent  = user.full_name;
    if (roleEl)  roleEl.textContent  = rm.en;
    if (deptEl)  deptEl.textContent  = user.department;
    if (avatarEl) avatarEl.textContent = user.full_name.charAt(0).toUpperCase();
    if (headerRole) headerRole.textContent = `${rm.en} | ${rm.ar}`;
  },

  _bindGlobalEvents() {
    // Login form
    document.getElementById("login-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      await Auth.handleLogin();
    });

    // Register form
    document.getElementById("register-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      await Auth.handleRegister();
    });

    // Role card selection
    document.querySelectorAll(".role-card").forEach(card => {
      card.addEventListener("click", () => {
        document.querySelectorAll(".role-card").forEach(c => c.classList.remove("selected"));
        card.classList.add("selected");
        document.getElementById("reg-role").value = card.dataset.role;
      });
    });

    // Sidebar toggle
    document.getElementById("sidebar-open-btn")?.addEventListener("click", () => {
      document.getElementById("sidebar").classList.remove("collapsed", "mobile-open");
      document.getElementById("sidebar").classList.add("mobile-open"); // mobile
      // Desktop: just remove collapsed
      if (window.innerWidth > 768) {
        document.getElementById("sidebar").classList.remove("collapsed");
        document.getElementById("sidebar").classList.remove("mobile-open");
      }
    });
    document.getElementById("sidebar-close-btn")?.addEventListener("click", () => {
      const s = document.getElementById("sidebar");
      s.classList.add("collapsed");
      s.classList.remove("mobile-open");
    });

    // New chat button
    document.getElementById("new-chat-btn")?.addEventListener("click", () => {
      Chat.startNewConversation();
    });

    // Logout
    document.getElementById("logout-btn")?.addEventListener("click", async () => {
      await API.logout();
      window.location.reload();
    });

    // Send message
    document.getElementById("send-btn")?.addEventListener("click", () => Chat.sendMessage());

    // Enter to send (Shift+Enter for newline)
    document.getElementById("message-input")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        Chat.sendMessage();
      }
    });

    // Auto-resize textarea + char count
    document.getElementById("message-input")?.addEventListener("input", () => {
      const ta = document.getElementById("message-input");
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
      const len = ta.value.length;
      document.getElementById("char-count").textContent = `${len} / 2000`;
      document.getElementById("send-btn").disabled = len === 0;
    });

    // Admin panel shortcut: Ctrl+Shift+A
    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey && e.shiftKey && e.key === "A") {
        e.preventDefault();
        Admin.openModal();
      }
    });
  },
};


/* ══════════════════════════════════════════════════════════════════
   AUTH MODULE
══════════════════════════════════════════════════════════════════ */
const Auth = {
  async handleLogin() {
    const eid = document.getElementById("login-eid").value.trim();
    const btn = document.getElementById("login-btn");
    const errEl = document.getElementById("login-error");

    if (!eid) {
      this._showError(errEl, "يرجى إدخال رقم الموظف / Please enter your Employee ID.");
      return;
    }

    btn.disabled = true;
    btn.querySelector(".ar").textContent = "جاري الدخول…";
    errEl.classList.add("hidden");

    const { ok, data } = await API.login(eid);

    btn.disabled = false;
    btn.querySelector(".ar").textContent = "دخول";

    if (ok) {
      App.enterChat(data.user);
    } else {
      this._showError(errEl, data.error || "فشل تسجيل الدخول / Login failed.");
    }
  },

  async handleRegister() {
    const name   = document.getElementById("reg-name").value.trim();
    const eid    = document.getElementById("reg-eid").value.trim();
    const dept   = document.getElementById("reg-dept").value;
    const role   = document.getElementById("reg-role").value;
    const title  = document.getElementById("reg-title").value.trim();
    const errEl  = document.getElementById("register-error");
    const btn    = document.getElementById("register-btn");

    if (!name || !eid || !dept || !role) {
      this._showError(errEl, "يرجى ملء جميع الحقول المطلوبة / Please fill all required fields.");
      return;
    }

    btn.disabled = true;
    btn.querySelector(".ar").textContent = "جاري الإنشاء…";
    errEl.classList.add("hidden");

    const { ok, data } = await API.register({ employee_id: eid, full_name: name, department: dept, role, job_title: title });

    btn.disabled = false;
    btn.querySelector(".ar").textContent = "إنشاء الحساب";

    if (ok) {
      App.enterChat(data.user);
    } else {
      this._showError(errEl, data.error || "فشل إنشاء الحساب / Registration failed.");
    }
  },

  _showError(el, msg) {
    el.textContent = msg;
    el.classList.remove("hidden");
    el.style.animation = "none";
    setTimeout(() => (el.style.animation = ""), 10);
  },
};


/* ══════════════════════════════════════════════════════════════════
   CHAT MODULE
══════════════════════════════════════════════════════════════════ */
const Chat = {
  currentConvId: null,
  isLoading: false,

  async init() {
    await this.loadConversations();
    await this.checkSystemStatus();
    // Poll status every 10 seconds
    setInterval(() => this.checkSystemStatus(), 10000);
  },

  async checkSystemStatus() {
    const { ok, data } = await API.adminStatus();
    const dot  = document.getElementById("status-dot");
    const text = document.getElementById("status-text");

    if (!ok) return;

    if (data.collection_ready) {
      dot.className  = "status-dot ready";
      text.textContent = "النظام جاهز / System Ready";
    } else if (data.state === "running") {
      dot.className  = "status-dot loading";
      text.textContent = `${data.progress || 0}% | جاري الاستيعاب…`;
    } else {
      dot.className  = "status-dot error";
      text.textContent = "قاعدة المعرفة غير جاهزة / KB not ready";
    }
  },

  async loadConversations() {
    const { ok, data } = await API.getConversations();
    const listEl = document.getElementById("conversations-list");
    if (!ok || !data.conversations) return;

    listEl.innerHTML = "";

    if (data.conversations.length === 0) {
      listEl.innerHTML = `<div class="conversations-empty">
        <span class="ar">لا توجد محادثات سابقة</span>
        <span class="en">No previous conversations</span>
      </div>`;
      return;
    }

    data.conversations.forEach(conv => {
      const item = document.createElement("div");
      item.className = "conv-item" + (conv.conversation_id === this.currentConvId ? " active" : "");
      item.dataset.convId = conv.conversation_id;
      const dateStr = conv.updated_at ? new Date(conv.updated_at).toLocaleDateString("ar-SA") : "";
      item.innerHTML = `
        <div class="conv-title">${this._esc(conv.title || "محادثة")}</div>
        <div class="conv-date">${dateStr}</div>
      `;
      item.addEventListener("click", () => this.loadConversation(conv.conversation_id));
      listEl.appendChild(item);
    });

    lucide.createIcons();
  },

  async loadConversation(convId) {
    this.currentConvId = convId;
    this._setActiveConv(convId);

    const welcome = document.getElementById("welcome-screen");
    const container = document.getElementById("messages-container");
    welcome.style.display = "none";
    container.innerHTML = "";

    const { ok, data } = await API.getMessages(convId);
    if (!ok) return;

    data.messages.forEach(msg => {
      const sources = msg.sources ? JSON.parse(msg.sources) : [];
      if (msg.role === "user") {
        this._appendUserMessage(msg.content, msg.timestamp);
      } else {
        this._appendAssistantMessage(msg.content, sources, msg.timestamp);
      }
    });

    this._scrollToBottom();
  },

  async startNewConversation() {
    this.currentConvId = null;
    const welcome = document.getElementById("welcome-screen");
    const container = document.getElementById("messages-container");
    welcome.style.display = "";
    container.innerHTML = "";
    this._setActiveConv(null);
    document.getElementById("message-input").focus();
  },

  useSuggestion(chipEl) {
    const ta = document.getElementById("message-input");
    ta.value = chipEl.textContent.trim();
    ta.dispatchEvent(new Event("input"));
    ta.focus();
  },

  async sendMessage() {
    if (this.isLoading) return;
    const ta = document.getElementById("message-input");
    const msg = ta.value.trim();
    if (!msg) return;

    // Reset input
    ta.value = "";
    ta.style.height = "auto";
    document.getElementById("char-count").textContent = "0 / 2000";
    document.getElementById("send-btn").disabled = true;

    // Hide welcome, show container
    document.getElementById("welcome-screen").style.display = "none";

    // Append user message
    this._appendUserMessage(msg);
    this._showTyping(true);
    this.isLoading = true;

    const { ok, data } = await API.chat(msg, this.currentConvId);

    this._showTyping(false);
    this.isLoading = false;

    if (ok) {
      this.currentConvId = data.conversation_id;
      this._appendAssistantMessage(data.answer, data.sources || []);
      await this.loadConversations(); // Refresh sidebar
    } else {
      const errMsg = data.message || data.error || "حدث خطأ غير متوقع / An unexpected error occurred.";
      this._appendAssistantMessage(`⚠️ ${errMsg}`, []);
    }

    this._scrollToBottom();
    ta.focus();
  },

  _appendUserMessage(content, timestamp = null) {
    const container = document.getElementById("messages-container");
    const timeStr = timestamp ? this._formatTime(timestamp) : this._formatTime(new Date().toISOString());
    const div = document.createElement("div");
    div.className = "message-wrapper user-msg";
    div.innerHTML = `
      <div class="bubble-row">
        <div class="bubble user-bubble">${this._esc(content)}</div>
      </div>
      <div class="message-time">${timeStr}</div>
    `;
    container.appendChild(div);
    this._scrollToBottom();
  },

  _appendAssistantMessage(content, sources = [], timestamp = null) {
    const container = document.getElementById("messages-container");
    const timeStr = timestamp ? this._formatTime(timestamp) : this._formatTime(new Date().toISOString());
    const formattedContent = this._formatAnswer(content);

    // Build citation HTML
    let citationHtml = "";
    if (sources && sources.length > 0) {
      const citId = "cit-" + Date.now();
      const items = sources.map(s => `
        <div class="citation-item">
          <span class="citation-icon">📄</span>
          <div class="citation-info">
            <div class="citation-file">${this._esc(s.file)}</div>
            <div class="citation-meta">
              <span class="ar">الصفحة / Page:</span> ${s.page} &nbsp;|&nbsp;
              <span class="ar">القسم:</span> ${this._esc(s.section || "—")}
            </div>
          </div>
          <span class="citation-relevance">${s.relevance}%</span>
        </div>
      `).join("");

      citationHtml = `
        <div class="citations-card">
          <button class="citation-toggle-btn" onclick="Chat._toggleCitation('${citId}', this)">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span class="ar">المراجع</span>
            <span class="en">References</span>
            (${sources.length})
          </button>
          <div class="citation-list" id="${citId}">
            ${items}
          </div>
        </div>
      `;
    }

    const div = document.createElement("div");
    div.className = "message-wrapper assistant-msg";
    div.innerHTML = `
      <div class="bubble-row">
        <div class="assistant-avatar">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="10" x="3" y="11" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" x2="8" y1="16" y2="16"/><line x1="16" x2="16" y1="16" y2="16"/></svg>
        </div>
        <div class="bubble assistant-bubble">${formattedContent}</div>
      </div>
      <div class="message-time">${timeStr}</div>
      ${citationHtml}
    `;
    container.appendChild(div);
    this._scrollToBottom();
  },

  _toggleCitation(citId, btn) {
    const list = document.getElementById(citId);
    if (!list) return;
    list.classList.toggle("open");
    const isOpen = list.classList.contains("open");
    const arSpan = btn.querySelector(".ar");
    if (arSpan) arSpan.textContent = isOpen ? "إخفاء المراجع" : "المراجع";
  },

  _showTyping(show) {
    const el = document.getElementById("typing-indicator");
    el.classList.toggle("hidden", !show);
    if (show) this._scrollToBottom();
  },

  _scrollToBottom() {
    const area = document.getElementById("messages-area");
    setTimeout(() => area.scrollTo({ top: area.scrollHeight, behavior: "smooth" }), 50);
  },

  _setActiveConv(convId) {
    document.querySelectorAll(".conv-item").forEach(el => {
      el.classList.toggle("active", el.dataset.convId === convId);
    });
  },

  _formatAnswer(text) {
    // Convert markdown-like bold **text** to <strong>
    let html = this._esc(text)
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/^(\d+)\.\s/gm, "<br><strong>$1.</strong> ")
      .replace(/\n/g, "<br>");
    return html;
  },

  _formatTime(isoStr) {
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" });
    } catch { return ""; }
  },

  _esc(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  },
};


/* ══════════════════════════════════════════════════════════════════
   ADMIN MODULE
══════════════════════════════════════════════════════════════════ */
const Admin = {
  _pollTimer: null,

  openModal() {
    document.getElementById("admin-modal").classList.remove("hidden");
    this._refreshStatus();
    lucide.createIcons();
  },

  closeModal() {
    document.getElementById("admin-modal").classList.add("hidden");
    clearInterval(this._pollTimer);
  },

  async _refreshStatus() {
    const { ok, data } = await API.adminStatus();
    const card = document.getElementById("admin-status-card");
    if (!ok) { card.innerHTML = "⚠️ Could not fetch status."; return; }

    const ready = data.collection_ready;
    const stateIcon = ready ? "✅" : (data.state === "running" ? "⏳" : "⚠️");
    const stateMsg  = ready
      ? `Knowledge base ready — ${data.total_chunks || "?"} chunks from ${data.total_docs || "?"} documents.`
      : (data.state === "running" ? `Ingesting... ${data.progress || 0}%` : data.message || "Not ingested.");

    card.innerHTML = `<span style="font-size:1.2rem">${stateIcon}</span> ${stateMsg}`;

    if (data.state === "running") {
      const wrap = document.getElementById("ingest-progress-wrap");
      wrap.classList.remove("hidden");
      document.getElementById("progress-bar").style.width = `${data.progress || 0}%`;
      document.getElementById("progress-label").textContent = data.message || "";
      this._pollTimer = setTimeout(() => this._refreshStatus(), 2000);
    } else {
      clearInterval(this._pollTimer);
    }
  },

  async triggerIngest() {
    const pw = document.getElementById("admin-password").value;
    const feedbackEl = document.getElementById("admin-feedback");
    const btn = document.getElementById("ingest-btn");

    if (!pw) {
      feedbackEl.className = "alert alert-error";
      feedbackEl.textContent = "Please enter the admin password.";
      feedbackEl.classList.remove("hidden");
      return;
    }

    btn.disabled = true;

    const { ok, data } = await API.triggerIngest(pw);
    btn.disabled = false;

    feedbackEl.classList.remove("hidden");
    if (ok) {
      feedbackEl.className = "alert alert-success";
      feedbackEl.textContent = "✅ Ingestion started! This may take several minutes depending on document size.";
      document.getElementById("ingest-progress-wrap").classList.remove("hidden");
      // Poll status
      this._pollTimer = setInterval(() => this._refreshStatus(), 2000);
    } else {
      feedbackEl.className = "alert alert-error";
      feedbackEl.textContent = `❌ ${data.error || "Failed to start ingestion."}`;
    }
  },
};

// Make Chat._toggleCitation accessible from inline onclick
window.Chat  = Chat;
window.Admin = Admin;
window.App   = App;
window.Auth  = Auth;
