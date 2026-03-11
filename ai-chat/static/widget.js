/**
 * KlipperOS-AI Chat Widget — Mainsail Entegrasyonu v2
 *
 * Ozellikler:
 *   - Quick actions (Durum): dogrudan Moonraker'dan, AI'ya gitmez (anlik)
 *   - AI chat: streaming SSE, Atom'da yavas (~2dk) oldugu icin timer gosterir
 *   - Responsive, dark theme, Mainsail ile uyumlu
 *
 * Kullanim:
 *   <script src="/ai-chat/widget.js" defer></script>
 */
(function () {
  "use strict";

  // --- CONFIG ---
  const AI_API = window.location.port === "8085"
    ? window.location.origin
    : window.location.origin + "/ai-chat";
  const WIDGET_ID = "klipperos-ai-widget";

  // Zaten yuklenmisse tekrar yukleme
  if (document.getElementById(WIDGET_ID)) return;

  // --- CSS INJECTION ---
  const style = document.createElement("style");
  style.textContent = `
    #${WIDGET_ID}-fab {
      position: fixed;
      bottom: 20px;
      right: 20px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: linear-gradient(135deg, #f5a623, #e6961a);
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 16px rgba(245,166,35,0.4);
      z-index: 9999;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 26px;
      transition: transform 0.2s, box-shadow 0.2s;
      animation: ${WIDGET_ID}-pulse 3s infinite;
    }
    #${WIDGET_ID}-fab:hover {
      transform: scale(1.1);
      box-shadow: 0 6px 24px rgba(245,166,35,0.6);
    }
    #${WIDGET_ID}-fab.open {
      animation: none;
      background: #e74c3c;
    }
    @keyframes ${WIDGET_ID}-pulse {
      0%, 100% { box-shadow: 0 4px 16px rgba(245,166,35,0.4); }
      50% { box-shadow: 0 4px 24px rgba(245,166,35,0.7); }
    }

    #${WIDGET_ID}-panel {
      position: fixed;
      bottom: 88px;
      right: 20px;
      width: 380px;
      height: 520px;
      background: #1e1e2e;
      border: 1px solid #3a3a5a;
      border-radius: 16px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5);
      z-index: 9998;
      display: none;
      flex-direction: column;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    #${WIDGET_ID}-panel.visible { display: flex; }

    .aiw-header {
      background: #181825;
      padding: 12px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid #3a3a5a;
      flex-shrink: 0;
    }
    .aiw-header-title {
      display: flex; align-items: center; gap: 8px;
      color: #f5a623; font-weight: 600; font-size: 14px;
    }
    .aiw-header-status {
      display: flex; gap: 8px; align-items: center;
    }
    .aiw-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: #e74c3c;
    }
    .aiw-dot.online { background: #4caf50; }
    .aiw-status-label { font-size: 11px; color: #a0a0b0; }

    .aiw-quick {
      display: flex; gap: 6px; padding: 8px 12px;
      overflow-x: auto; background: #181825;
      border-bottom: 1px solid #2a2a4a; flex-shrink: 0;
    }
    .aiw-quick::-webkit-scrollbar { height: 0; }
    .aiw-quick-btn {
      flex-shrink: 0; padding: 4px 10px; border-radius: 12px;
      border: 1px solid #3a3a5a; background: transparent;
      color: #c0c0d0; font-size: 11px; cursor: pointer;
      white-space: nowrap; transition: background 0.15s, color 0.15s;
    }
    .aiw-quick-btn:hover {
      background: #f5a623; color: #1e1e2e; border-color: #f5a623;
    }
    .aiw-quick-btn:disabled {
      opacity: 0.5; cursor: not-allowed;
    }

    .aiw-messages {
      flex: 1; overflow-y: auto; padding: 12px;
      display: flex; flex-direction: column; gap: 10px;
    }
    .aiw-messages::-webkit-scrollbar { width: 4px; }
    .aiw-messages::-webkit-scrollbar-thumb { background: #3a3a5a; border-radius: 4px; }

    .aiw-msg {
      max-width: 88%; padding: 8px 12px; border-radius: 12px;
      font-size: 13px; line-height: 1.5; word-break: break-word; color: #e0e0e0;
    }
    .aiw-msg.user {
      align-self: flex-end; background: #3b5998;
      border-bottom-right-radius: 4px;
    }
    .aiw-msg.ai {
      align-self: flex-start; background: #282840;
      border-bottom-left-radius: 4px;
    }
    .aiw-msg.ai pre {
      background: #1a1a2e; padding: 8px; border-radius: 6px;
      overflow-x: auto; font-size: 11px; margin: 6px 0;
    }
    .aiw-msg.ai code {
      background: #1a1a2e; padding: 1px 4px; border-radius: 3px; font-size: 12px;
    }
    .aiw-msg.system {
      align-self: flex-start; background: #1a2a1a;
      border: 1px solid #2a4a2a; border-bottom-left-radius: 4px;
    }

    .aiw-typing {
      align-self: flex-start; padding: 8px 16px;
      background: #282840; border-radius: 12px;
      font-size: 13px; color: #a0a0b0;
      display: flex; align-items: center; gap: 8px;
    }
    .aiw-typing-dots span {
      animation: ${WIDGET_ID}-blink 1.2s infinite;
    }
    .aiw-typing-dots span:nth-child(2) { animation-delay: 0.2s; }
    .aiw-typing-dots span:nth-child(3) { animation-delay: 0.4s; }
    .aiw-typing-timer {
      font-size: 10px; color: #666; margin-left: 4px;
    }
    @keyframes ${WIDGET_ID}-blink {
      0%, 100% { opacity: 0.3; } 50% { opacity: 1; }
    }

    .aiw-welcome {
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; flex: 1; gap: 8px;
      color: #a0a0b0; text-align: center; padding: 20px;
    }
    .aiw-welcome-icon { font-size: 40px; }
    .aiw-welcome h3 { color: #f5a623; font-size: 16px; font-weight: 600; margin: 0; }
    .aiw-welcome p { font-size: 12px; margin: 0; line-height: 1.4; }

    .aiw-input-area {
      display: flex; gap: 8px; padding: 10px 12px;
      border-top: 1px solid #3a3a5a; background: #181825; flex-shrink: 0;
    }
    .aiw-input {
      flex: 1; background: #282840; border: 1px solid #3a3a5a;
      border-radius: 20px; padding: 8px 14px; color: #e0e0e0;
      font-size: 13px; outline: none; resize: none;
      max-height: 80px; font-family: inherit;
    }
    .aiw-input::placeholder { color: #666; }
    .aiw-input:focus { border-color: #f5a623; }
    .aiw-send {
      width: 36px; height: 36px; border-radius: 50%;
      background: #f5a623; border: none; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      font-size: 16px; flex-shrink: 0; transition: background 0.15s;
    }
    .aiw-send:hover { background: #e6961a; }
    .aiw-send:disabled { background: #555; cursor: not-allowed; }

    @media (max-width: 480px) {
      #${WIDGET_ID}-panel {
        width: calc(100vw - 24px); height: calc(100vh - 120px);
        right: 12px; bottom: 80px; border-radius: 12px;
      }
    }
  `;
  document.head.appendChild(style);

  // --- HTML STRUCTURE ---
  const fab = document.createElement("button");
  fab.id = `${WIDGET_ID}-fab`;
  fab.innerHTML = "🤖";
  fab.title = "KlipperOS-AI Asistan";
  document.body.appendChild(fab);

  const panel = document.createElement("div");
  panel.id = `${WIDGET_ID}-panel`;
  panel.innerHTML = `
    <div class="aiw-header">
      <div class="aiw-header-title">🤖 KlipperOS-AI</div>
      <div class="aiw-header-status">
        <div class="aiw-dot" id="aiw-ollama-dot"></div>
        <span class="aiw-status-label" id="aiw-status-text">baglaniyor...</span>
      </div>
    </div>
    <div class="aiw-quick">
      <button class="aiw-quick-btn" data-action="quick-status">📊 Durum</button>
      <button class="aiw-quick-btn" data-q="Baski kalitesi sorunum var">🔧 Sorunlar</button>
      <button class="aiw-quick-btn" data-q="PID tuning nasil yapilir?">🌡️ PID</button>
      <button class="aiw-quick-btn" data-q="Tabla seviyeleme nasil yapilir?">📐 Leveling</button>
      <button class="aiw-quick-btn" data-q="Input shaper kalibrasyonu">📳 Shaper</button>
      <button class="aiw-quick-btn" data-q="Pressure advance ayari">💨 PA</button>
    </div>
    <div class="aiw-messages" id="aiw-messages">
      <div class="aiw-welcome" id="aiw-welcome">
        <div class="aiw-welcome-icon">🤖</div>
        <h3>KlipperOS-AI</h3>
        <p>3D yazici, Klipper ve sistem<br>konusunda yardima hazirim.</p>
      </div>
    </div>
    <div class="aiw-input-area">
      <textarea class="aiw-input" id="aiw-input" placeholder="Bir soru sorun..." rows="1"></textarea>
      <button class="aiw-send" id="aiw-send">➤</button>
    </div>
  `;
  document.body.appendChild(panel);

  // --- ELEMENTS ---
  const messagesEl = document.getElementById("aiw-messages");
  const welcomeEl = document.getElementById("aiw-welcome");
  const inputEl = document.getElementById("aiw-input");
  const sendBtn = document.getElementById("aiw-send");
  const ollamaDot = document.getElementById("aiw-ollama-dot");
  const statusText = document.getElementById("aiw-status-text");

  // --- STATE ---
  let history = [];
  let streaming = false;

  // --- TOGGLE ---
  fab.addEventListener("click", () => {
    const isOpen = panel.classList.toggle("visible");
    fab.classList.toggle("open", isOpen);
    fab.innerHTML = isOpen ? "✕" : "🤖";
    if (isOpen) { inputEl.focus(); checkOllama(); }
  });

  // --- STATUS CHECK ---
  async function checkOllama() {
    try {
      const r = await fetch(`${AI_API}/api/status`);
      const d = await r.json();
      ollamaDot.classList.toggle("online", d.ollama);
      statusText.textContent = d.ollama ? (d.model || "hazir") : "baglanti yok";
    } catch {
      ollamaDot.classList.remove("online");
      statusText.textContent = "AI servisi kapali";
    }
  }

  // --- MARKDOWN (basit) ---
  function miniMarkdown(text) {
    let html = text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code>${code.trim()}</code></pre>`);
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  function scrollDown() { messagesEl.scrollTop = messagesEl.scrollHeight; }

  function addMsg(role, content) {
    if (welcomeEl) welcomeEl.style.display = "none";
    const div = document.createElement("div");
    div.className = `aiw-msg ${role}`;
    div.innerHTML = role === "user"
      ? content.replace(/</g, "&lt;")
      : miniMarkdown(content);
    messagesEl.appendChild(div);
    scrollDown();
    return div;
  }

  // --- TYPING with TIMER ---
  let typingTimer = null;
  function addTyping(showTimer) {
    const div = document.createElement("div");
    div.className = "aiw-typing";
    div.id = "aiw-typing";
    div.innerHTML = `
      <span class="aiw-typing-dots"><span>●</span><span>●</span><span>●</span></span>
      ${showTimer ? '<span class="aiw-typing-timer" id="aiw-timer">0s</span>' : ''}
    `;
    messagesEl.appendChild(div);
    scrollDown();

    if (showTimer) {
      let sec = 0;
      typingTimer = setInterval(() => {
        sec++;
        const el = document.getElementById("aiw-timer");
        if (el) {
          el.textContent = sec < 60 ? `${sec}s` : `${Math.floor(sec/60)}m${sec%60}s`;
          if (sec === 5) el.textContent += " ⏳";
          if (sec === 30) el.textContent += " (model yukluyor...)";
          if (sec === 90) el.textContent = `${Math.floor(sec/60)}m${sec%60}s (Atom yavas, bekleyin)`;
        }
      }, 1000);
    }
  }
  function removeTyping() {
    if (typingTimer) { clearInterval(typingTimer); typingTimer = null; }
    const t = document.getElementById("aiw-typing");
    if (t) t.remove();
  }

  // --- QUICK STATUS (no AI, instant) ---
  async function quickStatus() {
    if (streaming) return;
    streaming = true;
    setQuickBtnsDisabled(true);

    addMsg("user", "📊 Yazici Durumu");
    addTyping(false);

    try {
      const r = await fetch(`${AI_API}/api/quick-status`);
      removeTyping();
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      addMsg("system", d.text || "Durum alinamadi");
    } catch (err) {
      removeTyping();
      addMsg("ai", `⚠️ Durum hatasi: ${err.message}`);
    } finally {
      streaming = false;
      setQuickBtnsDisabled(false);
    }
  }

  // --- AI CHAT SEND (streaming SSE, with timer) ---
  async function send(text) {
    if (!text.trim() || streaming) return;
    streaming = true;
    sendBtn.disabled = true;
    setQuickBtnsDisabled(true);

    addMsg("user", text);
    history.push({ role: "user", content: text });
    addTyping(true); // show timer for AI

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 min timeout

      const resp = await fetch(`${AI_API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history.slice(-6) }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      removeTyping();
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let aiText = "";
      let bubble = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);
          if (data === "[DONE]") break;
          try {
            const p = JSON.parse(data);
            if (p.token) {
              aiText += p.token;
              if (!bubble) bubble = addMsg("ai", aiText);
              else bubble.innerHTML = miniMarkdown(aiText);
              scrollDown();
            }
            if (p.error) {
              aiText += `\n⚠️ ${p.error}`;
              if (bubble) bubble.innerHTML = miniMarkdown(aiText);
            }
          } catch {}
        }
      }

      if (aiText) history.push({ role: "assistant", content: aiText });
      if (history.length > 12) history = history.slice(-12);
    } catch (err) {
      removeTyping();
      if (err.name === "AbortError") {
        addMsg("ai", "⏰ Zaman asimi — model cok yavas yanit veriyor. Tekrar deneyin.");
      } else {
        addMsg("ai", `⚠️ Baglanti hatasi: ${err.message}`);
      }
    } finally {
      streaming = false;
      sendBtn.disabled = false;
      setQuickBtnsDisabled(false);
      inputEl.focus();
    }
  }

  // --- Helper: quick buttons disable/enable ---
  function setQuickBtnsDisabled(val) {
    panel.querySelectorAll(".aiw-quick-btn").forEach(b => b.disabled = val);
  }

  // --- EVENTS ---
  sendBtn.addEventListener("click", () => {
    send(inputEl.value); inputEl.value = "";
  });
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault(); send(inputEl.value); inputEl.value = "";
    }
  });

  // Quick action buttons
  panel.querySelectorAll(".aiw-quick-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.action === "quick-status") {
        quickStatus();
      } else if (btn.dataset.q) {
        send(btn.dataset.q);
      }
    });
  });

  // Auto-resize textarea
  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 80) + "px";
  });

  // Initial + periodic status check
  setTimeout(checkOllama, 2000);
  setInterval(checkOllama, 30000);
})();
