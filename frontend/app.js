/**
 * Estados Judiciales IA - Chat Application
 * Microstack 1: Frontend (conectará con backend IA en microstack 2)
 */

// API endpoint - se configura desde config.js (generado en deploy) o usa fallback
const API_BASE = window.APP_CONFIG?.apiEndpoint || "/api";

// DOM Elements
const chatContainer = document.getElementById("chat-container");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");

// State
let isWaiting = false;

// ============================================
// Chat Logic
// ============================================

function addMessage(content, role = "assistant") {
  const messageEl = document.createElement("div");
  messageEl.className = `message message-${role}`;

  const avatar = role === "user" ? getUserAvatar() : getAssistantAvatar();

  messageEl.innerHTML = `
    <div class="message-avatar" aria-hidden="true">${avatar}</div>
    <div class="message-content">${formatContent(content)}</div>
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
        <span></span><span></span><span></span>
      </div>
    </div>
  `;

  chatContainer.appendChild(messageEl);
  scrollToBottom();
}

function removeTypingIndicator() {
  const indicator = document.getElementById("typing-indicator");
  if (indicator) indicator.remove();
}

function formatContent(content) {
  if (typeof content === "string") {
    return content
      .split("\n")
      .map((line) => `<p>${escapeHtml(line)}</p>`)
      .join("");
  }
  return content;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
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

  addMessage(userMessage, "user");
  messageInput.value = "";
  adjustTextareaHeight();
  updateSendButton();

  isWaiting = true;
  addTypingIndicator();

  try {
    const response = await fetchAIResponse(userMessage);
    removeTypingIndicator();
    addMessage(response, "assistant");
  } catch (error) {
    removeTypingIndicator();
    addMessage(getErrorMessage(error), "assistant");
  } finally {
    isWaiting = false;
    messageInput.focus();
  }
}

async function fetchAIResponse(message) {
  try {
    const res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    return `<p>${escapeHtml(data.response)}</p>`;
  } catch (error) {
    // Fallback a respuestas simuladas si la API no está disponible
    console.warn("API no disponible, usando respuestas simuladas:", error.message);
    await simulateDelay(800);
    return getSimulatedResponse(message);
  }
}

function getSimulatedResponse(message) {
  const lowerMsg = message.toLowerCase();

  if (lowerMsg.includes("radicado") || lowerMsg.match(/\d{4}-\d+/)) {
    const radicado = message.match(/\d{4,}-?\d*/)?.[0] || "2023-00145";
    return buildResultsHTML(radicado);
  }

  if (lowerMsg.includes("juzgado") || lowerMsg.includes("juzgados")) {
    return `<p>Estos son los juzgados disponibles para consulta:</p>
      <ul>
        <li>Juzgado Promiscuo Municipal de Contadero</li>
        <li>Juzgado Promiscuo Municipal de Córdoba</li>
        <li>Juzgado Promiscuo Municipal de Cumbal</li>
        <li>Juzgado Promiscuo Municipal de Guachucal</li>
        <li>Juzgado Promiscuo Municipal de Potosí</li>
        <li>Juzgado Promiscuo Municipal de Pupiales</li>
        <li>Juzgado 1° Civil Municipal de Ipiales</li>
        <li>Juzgado 2° Civil Municipal de Ipiales</li>
      </ul>
      <p>¿Sobre cuál juzgado quieres consultar?</p>`;
  }

  if (lowerMsg.includes("ayuda") || lowerMsg.includes("help")) {
    return `<p>Puedo ayudarte con:</p>
      <ul>
        <li><strong>Buscar por radicado:</strong> Escribe el número (ej: 2023-00145)</li>
        <li><strong>Consultar juzgados:</strong> Pregunta "¿qué juzgados hay?"</li>
        <li><strong>Estado de un proceso:</strong> Dime el radicado y el juzgado</li>
      </ul>
      <p>También puedes adjuntar un documento PDF con estados para buscar radicados específicos.</p>`;
  }

  return `<p>Entendido. Para buscar información sobre estados judiciales, necesito que me proporciones:</p>
    <ul>
      <li>El <strong>número de radicado</strong> del proceso</li>
      <li>O el <strong>nombre del juzgado</strong> que quieres consultar</li>
    </ul>
    <p>¿Qué información tienes disponible?</p>`;
}

function buildResultsHTML(radicado) {
  return `<p>Encontré información para el radicado <code>${escapeHtml(radicado)}</code>:</p>
    <table class="results-table">
      <thead>
        <tr>
          <th>Radicado</th>
          <th>Juzgado</th>
          <th>Estado</th>
          <th>Fecha</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>${escapeHtml(radicado)}</td>
          <td>J.P.M. Contadero</td>
          <td><span class="status-badge status-badge--success">Publicado</span></td>
          <td>2025-07-04</td>
        </tr>
      </tbody>
    </table>
    <p>¿Necesitas más detalles sobre este proceso o buscar otro radicado?</p>`;
}

function getErrorMessage(error) {
  console.error("Chat error:", error);
  return `<p>⚠️ Lo siento, hubo un error al procesar tu consulta. Por favor intenta de nuevo.</p>
    <p><small>Si el problema persiste, verifica tu conexión a internet.</small></p>`;
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

function simulateDelay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
  if (message && !isWaiting) {
    sendMessage(message);
  }
});

messageInput.addEventListener("input", () => {
  adjustTextareaHeight();
  updateSendButton();
});

messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    const message = messageInput.value.trim();
    if (message && !isWaiting) {
      sendMessage(message);
    }
  }
});

// Initial focus
messageInput.focus();
