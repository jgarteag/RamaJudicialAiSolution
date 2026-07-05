/**
 * Estados Judiciales IA - Chat Application
 * Features: markdown rendering, juzgado selector, multi-format upload
 */

const API_BASE = window.APP_CONFIG?.apiEndpoint || "/api";

// DOM Elements
const chatContainer = document.getElementById("chat-container");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const fileInput = document.getElementById("file-input");
const uploadBtn = document.getElementById("upload-btn");
const juzgadoSelect = document.getElementById("juzgado-select");
const toolbarInfo = document.getElementById("toolbar-info");

// State
let isWaiting = false;

// ============================================
// Initialize
// ============================================

async function init() {
  await loadJuzgados();
}

async function loadJuzgados() {
  try {
    const res = await fetch(`${API_BASE}/juzgados`);
    if (!res.ok) throw new Error("Failed to load");
    const data = await res.json();

    data.juzgados.forEach((j) => {
      const opt = document.createElement("option");
      opt.value = j;
      opt.textContent = j;
      juzgadoSelect.appendChild(opt);
    });

    toolbarInfo.textContent = `${data.total} juzgados disponibles`;
  } catch (e) {
    console.warn("No se pudieron cargar juzgados:", e.message);
    toolbarInfo.textContent = "⚠️ Sin conexión a BD";
  }
}

// ============================================
// Markdown Rendering
// ============================================

function renderMarkdown(text) {
  if (typeof marked !== "undefined" && marked.parse) {
    return marked.parse(text);
  }
  // Fallback: basic formatting
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

// ============================================
// Chat Logic
// ============================================

function addMessage(content, role = "assistant", isMarkdown = false) {
  const messageEl = document.createElement("div");
  messageEl.className = `message message-${role}`;

  const avatar = role === "user" ? getUserAvatar() : getAssistantAvatar();
  const rendered = isMarkdown ? renderMarkdown(content) : content;

  messageEl.innerHTML = `
    <div class="message-avatar" aria-hidden="true">${avatar}</div>
    <div class="message-content markdown-body">${rendered}</div>
  `;

  chatContainer.appendChild(messageEl);
  scrollToBottom();
  return messageEl;
}

function addTypingIndicator() {
  const messageEl = document.createElement("div");
  messageEl.className = "message message-assistant";
  messageEl.id = "typing-indicator";
  messageEl.innerHTML = `
    <div class="message-avatar" aria-hidden="true">${getAssistantAvatar()}</div>
    <div class="message-content">
      <div class="typing-indicator"><span></span><span></span><span></span></div>
    </div>
  `;
  chatContainer.appendChild(messageEl);
  scrollToBottom();
}

function removeTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    chatContainer.scrollTop = chatContainer.scrollHeight;
  });
}

// ============================================
// API Communication
// ============================================

async function sendMessage(userMessage) {
  if (isWaiting) return;

  addMessage(`<p>${escapeHtml(userMessage)}</p>`, "user");
  messageInput.value = "";
  adjustTextareaHeight();
  updateSendButton();

  isWaiting = true;
  addTypingIndicator();

  try {
    const res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: userMessage }),
    });

    removeTypingIndicator();

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    addMessage(data.response, "assistant", true);
  } catch (error) {
    removeTypingIndicator();
    addMessage(`⚠️ Error: ${error.message}. Intenta de nuevo.`, "assistant", true);
  } finally {
    isWaiting = false;
    messageInput.focus();
  }
}

// ============================================
// File Upload (multi-format)
// ============================================

async function uploadFile(file) {
  if (isWaiting) return;

  const ext = file.name.split(".").pop().toLowerCase();
  const icon = ext === "pdf" ? "📄" : ext === "docx" || ext === "doc" ? "📝" : "📋";
  const juzgado = juzgadoSelect.value;
  const filterText = juzgado ? ` → Juzgado: <strong>${escapeHtml(juzgado)}</strong>` : " → Todos los juzgados";

  addMessage(`<p>${icon} <strong>${escapeHtml(file.name)}</strong> (${formatSize(file.size)})${filterText}</p>`, "user");

  isWaiting = true;
  addTypingIndicator();

  try {
    const base64 = await fileToBase64(file);

    const payload = {
      file: base64,
      filename: file.name,
    };
    if (juzgado) payload.juzgado = juzgado;

    const res = await fetch(`${API_BASE}/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    removeTypingIndicator();

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.error || `HTTP ${res.status}`);
    }

    const data = await res.json();

    // Build response: AI markdown + results table
    let html = renderMarkdown(data.response);

    if (data.matches && data.matches.length > 0) {
      html += `<table class="results-table">
        <thead><tr><th>Radicado</th><th>Juzgado</th><th>Relación</th><th>Año</th></tr></thead>
        <tbody>`;
      for (const match of data.matches) {
        html += `<tr>
          <td><code>${escapeHtml(match.radicado || "")}</code></td>
          <td>${escapeHtml(match.juzgado || match.tipo || "")}</td>
          <td>${escapeHtml(match.relacion || "N/A")}</td>
          <td>${match.ano_estado || ""}</td>
        </tr>`;
      }
      html += `</tbody></table>`;
    }

    const msgEl = document.createElement("div");
    msgEl.className = "message message-assistant";
    msgEl.innerHTML = `
      <div class="message-avatar" aria-hidden="true">${getAssistantAvatar()}</div>
      <div class="message-content markdown-body">${html}</div>
    `;
    chatContainer.appendChild(msgEl);
    scrollToBottom();
  } catch (error) {
    removeTypingIndicator();
    addMessage(`⚠️ Error al procesar el archivo: ${error.message}`, "assistant", true);
  } finally {
    isWaiting = false;
    fileInput.value = "";
    messageInput.focus();
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

// ============================================
// UI Helpers
// ============================================

function adjustTextareaHeight() {
  messageInput.style.height = "auto";
  messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + "px";
}

function updateSendButton() {
  sendBtn.disabled = !messageInput.value.trim() || isWaiting;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function getAssistantAvatar() {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <circle cx="12" cy="12" r="10"/>
    <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
    <line x1="9" y1="9" x2="9.01" y2="9"/>
    <line x1="15" y1="9" x2="15.01" y2="9"/>
  </svg>`;
}

function getUserAvatar() {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
    <circle cx="12" cy="7" r="4"/>
  </svg>`;
}

// ============================================
// Event Listeners
// ============================================

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = messageInput.value.trim();
  if (message && !isWaiting) sendMessage(message);
});

messageInput.addEventListener("input", () => {
  adjustTextareaHeight();
  updateSendButton();
});

messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    const message = messageInput.value.trim();
    if (message && !isWaiting) sendMessage(message);
  }
});

uploadBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const validTypes = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
  ];
  const ext = file.name.split(".").pop().toLowerCase();
  const validExts = ["pdf", "docx", "doc", "txt"];

  if (!validTypes.includes(file.type) && !validExts.includes(ext)) {
    addMessage("⚠️ Formato no soportado. Usa **PDF**, **Word** (.docx) o **TXT**.", "assistant", true);
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    addMessage("⚠️ El archivo es demasiado grande (máximo **10MB**).", "assistant", true);
    return;
  }
  uploadFile(file);
});

// Initialize on load
init();
