import { create } from 'zustand'
import { WS_URL } from '../config'

// WebSocket reconnection configuration
const WS_RECONNECT_CONFIG = {
  initialDelay: 1000,      // 1 second
  maxDelay: 30000,         // 30 seconds max
  backoffFactor: 1.5,      // Exponential backoff multiplier
  maxAttempts: Infinity,   // Keep trying forever
}

// Module-level state for reconnection (outside of Zustand to avoid issues)
let reconnectAttempts = 0
let reconnectTimeoutId = null
let shouldReconnect = true

export const useAlertStore = create((set, get) => ({
  // Connection state
  connected: false,
  reconnecting: false,
  socket: null,
  
  // Active alerts
  activeAlerts: [],
  alertHistory: [],
  
  // Calculate reconnect delay with exponential backoff
  _getReconnectDelay: () => {
    const delay = Math.min(
      WS_RECONNECT_CONFIG.initialDelay * Math.pow(WS_RECONNECT_CONFIG.backoffFactor, reconnectAttempts),
      WS_RECONNECT_CONFIG.maxDelay
    )
    return delay
  },
  
  // Connect to WebSocket
  connect: () => {
    const state = get()
    if (state.socket && state.socket.readyState === WebSocket.OPEN) return
    
    // Clear any pending reconnection
    if (reconnectTimeoutId) {
      clearTimeout(reconnectTimeoutId)
      reconnectTimeoutId = null
    }
    
    shouldReconnect = true
    
    try {
      const socket = new WebSocket(`${WS_URL}/api/streams/alerts`)
      
      socket.onopen = () => {
        console.log('🐱 Alert WebSocket connected')
        reconnectAttempts = 0
        set({ connected: true, reconnecting: false, socket })
      }
      
      socket.onclose = (event) => {
        console.log('🐱 Alert WebSocket disconnected', event.code, event.reason)
        set({ connected: false, socket: null })
        
        // Attempt to reconnect if we should
        if (shouldReconnect && reconnectAttempts < WS_RECONNECT_CONFIG.maxAttempts) {
          const delay = get()._getReconnectDelay()
          reconnectAttempts += 1
          set({ reconnecting: true })
          
          console.log(`🐱 Alert WebSocket reconnecting in ${delay}ms (attempt ${reconnectAttempts})`)
          reconnectTimeoutId = setTimeout(() => get().connect(), delay)
        }
      }
      
      socket.onerror = (error) => {
        console.error('🐱 Alert WebSocket error:', error)
      }
      
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          
          // Handle ping/pong keepalive
          if (data.type === 'ping') {
            return
          }
          
          if (data.type === 'alert_triggered') {
            // Add to active alerts
            set(state => ({
              activeAlerts: [...state.activeAlerts, {
                id: data.alert_id,
                ruleId: data.rule_id,
                ruleName: data.rule_name,
                cameraId: data.camera_id,
                message: data.message,
                confidence: data.confidence,
                detectedObjects: data.detected_objects,
                triggeredAt: new Date(),
              }],
              alertHistory: [{
                ...data,
                triggeredAt: new Date(),
              }, ...state.alertHistory.slice(0, 99)],
            }))
            
            // Play alert sound
            playAlertSound()
            
          } else if (data.type === 'alert_ended') {
            // Remove from active alerts
            set(state => ({
              activeAlerts: state.activeAlerts.filter(a => a.id !== data.alert_id),
            }))
          }
        } catch (e) {
          console.error('🐱 Alert WebSocket message parse error:', e)
        }
      }
      
      set({ socket })
    } catch (e) {
      console.error('🐱 Alert WebSocket connection error:', e)
      // Schedule reconnection on error
      if (shouldReconnect) {
        const delay = get()._getReconnectDelay()
        reconnectAttempts += 1
        set({ reconnecting: true })
        reconnectTimeoutId = setTimeout(() => get().connect(), delay)
      }
    }
  },
  
  // Disconnect
  disconnect: () => {
    shouldReconnect = false
    reconnectAttempts = 0
    
    if (reconnectTimeoutId) {
      clearTimeout(reconnectTimeoutId)
      reconnectTimeoutId = null
    }
    
    const { socket } = get()
    if (socket) {
      socket.close()
      set({ socket: null, connected: false, reconnecting: false })
    }
  },
  
  // Clear history
  clearHistory: () => set({ alertHistory: [] }),
}))

// Simple alert sound
function playAlertSound() {
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)()
    const oscillator = audioContext.createOscillator()
    const gainNode = audioContext.createGain()
    
    oscillator.connect(gainNode)
    gainNode.connect(audioContext.destination)
    
    oscillator.frequency.value = 800
    oscillator.type = 'sine'
    gainNode.gain.value = 0.3
    
    oscillator.start()
    
    // Quick beep pattern
    setTimeout(() => oscillator.frequency.value = 1000, 100)
    setTimeout(() => oscillator.frequency.value = 800, 200)
    setTimeout(() => {
      oscillator.stop()
      audioContext.close()
    }, 300)
  } catch (e) {
    console.log('Could not play alert sound:', e)
  }
}

