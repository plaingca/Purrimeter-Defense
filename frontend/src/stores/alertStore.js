import { create } from 'zustand'
import { WS_URL } from '../config'

export const useAlertStore = create((set, get) => ({
  // Connection state
  connected: false,
  socket: null,
  
  // Active alerts
  activeAlerts: [],
  alertHistory: [],
  
  // Connect to WebSocket
  connect: () => {
    if (get().socket) return
    
    const socket = new WebSocket(`${WS_URL}/api/streams/alerts`)
    
    socket.onopen = () => {
      console.log('🐱 Alert WebSocket connected')
      set({ connected: true, socket })
    }
    
    socket.onclose = () => {
      console.log('🐱 Alert WebSocket disconnected')
      set({ connected: false, socket: null })
      
      // Reconnect after delay
      setTimeout(() => get().connect(), 5000)
    }
    
    socket.onerror = (error) => {
      console.error('Alert WebSocket error:', error)
    }
    
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data)
      
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
    }
    
    set({ socket })
  },
  
  // Disconnect
  disconnect: () => {
    const { socket } = get()
    if (socket) {
      socket.close()
      set({ socket: null, connected: false })
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

