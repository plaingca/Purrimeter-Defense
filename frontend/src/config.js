/**
 * Configuration for Purrimeter Defense frontend
 * Uses environment variables with smart fallbacks to current hostname
 */

// Get the API URL - uses env var or falls back to current hostname
export const getApiUrl = () => {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL
  }
  const host = import.meta.env.VITE_HOST_DOMAIN || window.location.hostname
  return `${window.location.protocol}//${host}:8000`
}

// Get the WebSocket URL - uses env var or falls back to current hostname
export const getWsUrl = () => {
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = import.meta.env.VITE_HOST_DOMAIN || window.location.hostname
  return `${protocol}//${host}:8000`
}

// Export static values (computed once at load time)
export const API_URL = getApiUrl()
export const WS_URL = getWsUrl()

