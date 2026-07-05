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
const themeToggle = document.getElementById("theme-toggle");
const toastsContainer = document.getElementById("toasts-container");

// State
let isWaiting = false;

// ============================================
// Toast Notifications
// ============================================

function showToast(message, type = "info", duration = 3000) {
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;

  const icons = {
    success: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`,
    error: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
    warning: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`
  };

  toast.innerHTML = `
    <div class="toast-icon">${icons[type] || icons.info}</div>
    <span class="toast-message">${message}</span>
    <button class="toast-close" aria-label="Cerrar notificación">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>
  `;

  toastsContainer.appendChild(toast);

  const closeToast = () => {
    toast.classList.add("removing");
    setTimeout(() => toast.remove(), 300);
  };

  toast.querySelector(".toast-close").addEventListener("click", closeToast);

  if (duration > 0) {
    setTimeout(closeToast, duration);
  }

  return toast;
}

// ============================================
// Theme Management
// ============================================

function initTheme() {
  const saved = localStorage.getItem("theme");
  const prefer = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  const theme = saved || prefer;
  applyTheme(theme);
}

function applyTheme(theme) {
  document.documentElement.className = theme;
  localStorage.setItem("theme", theme);
}

function toggleTheme() {
  const current = document.documentElement.className || "light";
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
}

// ============================================
// Copy to Clipboard
// ============================================

function setupCopyButtons() {
  document.querySelectorAll(".copy-btn").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const value = btn.dataset.value;
      try {
        await navigator.clipboard.writeText(value);
        const originalSvg = btn.innerHTML;
        btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
        btn.classList.add("copied");
        setTimeout(() => {
          btn.innerHTML = originalSvg;
          btn.classList.remove("copied");
        }, 2000);
      } catch (err) {
        console.error("Copy failed:", err);
      }
    });
  });
}

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
      <div class="typing-indicator">
        <span></span>
        <span></span>
        <span></span>
        <span class="typing-text">Procesando...</span>
      </div>
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
      html += `<div class="results-container">
        <table class="results-table">
          <thead><tr>
            <th>Radicado</th>
            <th>Juzgado</th>
            <th>Relación</th>
            <th>Año</th>
            <th class="actions-col">Acciones</th>
          </tr></thead>
          <tbody>`;
      for (let i = 0; i < data.matches.length; i++) {
        const match = data.matches[i];
        const rowId = `result-${i}`;
        html += `<tr class="result-row" data-row-id="${rowId}">
          <td><code class="radicado-code">${escapeHtml(match.radicado || "")}</code></td>
          <td>${escapeHtml(match.juzgado || match.tipo || "")}</td>
          <td><span class="relacion-badge">${escapeHtml(match.relacion || "N/A")}</span></td>
          <td>${match.ano_estado || ""}</td>
          <td class="actions-cell">
            <button class="copy-btn" data-value="${escapeHtml(match.radicado || "")}" title="Copiar radicado">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
                <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
              </svg>
            </button>
          </td>
        </tr>`;
      }
      html += `</tbody></table></div>`;
    }

    const msgEl = document.createElement("div");
    msgEl.className = "message message-assistant";
    msgEl.innerHTML = `
      <div class="message-avatar" aria-hidden="true">${getAssistantAvatar()}</div>
      <div class="message-content markdown-body">${html}</div>
    `;
    chatContainer.appendChild(msgEl);
    setupCopyButtons();
    scrollToBottom();

    if (data.matches && data.matches.length > 0) {
      showToast(`✓ Se encontraron ${data.matches.length} resultado${data.matches.length !== 1 ? 's' : ''}`, "success");
    }
  } catch (error) {
    removeTypingIndicator();
    addMessage(`⚠️ Error al procesar el archivo: ${error.message}`, "assistant", true);
    showToast(`Error: ${error.message}`, "error", 4000);
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

themeToggle.addEventListener("click", toggleTheme);

// Initialize on load
initTheme();
init();
