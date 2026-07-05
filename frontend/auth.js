/**
 * Auth module - Cognito authentication via InitiateAuth API
 * Uses AWS Cognito User Pools directly (no SDK dependency)
 */

const AUTH_CONFIG = window.APP_CONFIG?.cognito || {};
const COGNITO_ENDPOINT = `https://cognito-idp.${AUTH_CONFIG.region || "us-east-1"}.amazonaws.com/`;

// State
let currentToken = localStorage.getItem("auth_token") || null;
let refreshToken = localStorage.getItem("refresh_token") || null;
let tokenExpiry = parseInt(localStorage.getItem("token_expiry") || "0", 10);
let currentUser = localStorage.getItem("auth_user") || null;

// ============================================
// Public API
// ============================================

function isAuthenticated() {
  if (!currentToken) return false;
  if (Date.now() > tokenExpiry) {
    // Try to refresh
    if (refreshToken) {
      refreshSession();
      return !!currentToken;
    }
    logout();
    return false;
  }
  return true;
}

function getToken() {
  if (!isAuthenticated() && refreshToken) {
    // Will be refreshed on next API call
    return currentToken;
  }
  return currentToken;
}

function getUser() {
  return currentUser;
}

async function login(email, password) {
  const payload = {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: AUTH_CONFIG.clientId,
    AuthParameters: {
      USERNAME: email,
      PASSWORD: password,
    },
  };

  const response = await cognitoRequest("InitiateAuth", payload);

  if (response.ChallengeName === "NEW_PASSWORD_REQUIRED") {
    throw new Error("NEW_PASSWORD_REQUIRED");
  }

  if (response.AuthenticationResult) {
    saveSession(response.AuthenticationResult, email);
    return { success: true, user: email };
  }

  throw new Error("Error de autenticación");
}

async function signUp(email, password) {
  const payload = {
    ClientId: AUTH_CONFIG.clientId,
    Username: email,
    Password: password,
    UserAttributes: [{ Name: "email", Value: email }],
  };

  await cognitoRequest("SignUp", payload);
  return { success: true, message: "Revisa tu email para el código de verificación" };
}

async function confirmSignUp(email, code) {
  const payload = {
    ClientId: AUTH_CONFIG.clientId,
    Username: email,
    ConfirmationCode: code,
  };

  await cognitoRequest("ConfirmSignUp", payload);
  return { success: true };
}

async function refreshSession() {
  if (!refreshToken) return;

  try {
    const payload = {
      AuthFlow: "REFRESH_TOKEN_AUTH",
      ClientId: AUTH_CONFIG.clientId,
      AuthParameters: {
        REFRESH_TOKEN: refreshToken,
      },
    };

    const response = await cognitoRequest("InitiateAuth", payload);
    if (response.AuthenticationResult) {
      saveSession(response.AuthenticationResult, currentUser);
    }
  } catch (e) {
    console.warn("Token refresh failed:", e.message);
    logout();
  }
}

function logout() {
  currentToken = null;
  refreshToken = null;
  tokenExpiry = 0;
  currentUser = null;
  localStorage.removeItem("auth_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("token_expiry");
  localStorage.removeItem("auth_user");
}

// ============================================
// Internal
// ============================================

function saveSession(authResult, email) {
  currentToken = authResult.IdToken || authResult.AccessToken;
  refreshToken = authResult.RefreshToken || refreshToken;
  tokenExpiry = Date.now() + (authResult.ExpiresIn || 3600) * 1000;
  currentUser = email;

  localStorage.setItem("auth_token", currentToken);
  if (authResult.RefreshToken) localStorage.setItem("refresh_token", refreshToken);
  localStorage.setItem("token_expiry", tokenExpiry.toString());
  localStorage.setItem("auth_user", email);
}

async function cognitoRequest(action, payload) {
  const res = await fetch(COGNITO_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": `AWSCognitoIdentityProviderService.${action}`,
    },
    body: JSON.stringify(payload),
  });

  const data = await res.json();

  if (!res.ok) {
    const errorType = data.__type || "";
    const errorMsg = data.message || data.Message || "Error desconocido";

    if (errorType.includes("NotAuthorizedException")) {
      throw new Error("Email o contraseña incorrectos");
    }
    if (errorType.includes("UserNotConfirmedException")) {
      throw new Error("CONFIRM_REQUIRED");
    }
    if (errorType.includes("UsernameExistsException")) {
      throw new Error("Este email ya está registrado");
    }
    if (errorType.includes("InvalidPasswordException")) {
      throw new Error("La contraseña debe tener mínimo 8 caracteres, mayúsculas y números");
    }
    if (errorType.includes("CodeMismatchException")) {
      throw new Error("Código de verificación incorrecto");
    }
    if (errorType.includes("ExpiredCodeException")) {
      throw new Error("El código ha expirado. Solicita uno nuevo.");
    }

    throw new Error(errorMsg);
  }

  return data;
}
