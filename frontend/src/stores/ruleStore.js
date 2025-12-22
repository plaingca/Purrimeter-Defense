import { create } from 'zustand'
import { API_URL } from '../config'

export const useRuleStore = create((set, get) => ({
  rules: [],
  presets: [],
  loading: false,
  error: null,
  
  // Fetch all rules
  fetchRules: async (cameraId = null) => {
    set({ loading: true, error: null })
    try {
      const url = cameraId 
        ? `${API_URL}/api/rules/?camera_id=${cameraId}`
        : `${API_URL}/api/rules/`
      const response = await fetch(url)
      if (!response.ok) throw new Error('Failed to fetch rules')
      const rules = await response.json()
      set({ rules, loading: false })
    } catch (error) {
      set({ error: error.message, loading: false })
    }
  },
  
  // Fetch presets
  fetchPresets: async () => {
    try {
      const response = await fetch(`${API_URL}/api/rules/presets/list`)
      if (!response.ok) throw new Error('Failed to fetch presets')
      const presets = await response.json()
      set({ presets })
    } catch (error) {
      console.error('Preset fetch error:', error)
    }
  },
  
  // Add rule
  addRule: async (ruleData) => {
    try {
      const response = await fetch(`${API_URL}/api/rules/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(ruleData),
      })
      if (!response.ok) throw new Error('Failed to add rule')
      const rule = await response.json()
      set(state => ({ rules: [...state.rules, rule] }))
      return rule
    } catch (error) {
      set({ error: error.message })
      throw error
    }
  },
  
  // Apply preset
  applyPreset: async (presetId, cameraId) => {
    try {
      const response = await fetch(
        `${API_URL}/api/rules/presets/${presetId}/apply?camera_id=${cameraId}`,
        { method: 'POST' }
      )
      if (!response.ok) throw new Error('Failed to apply preset')
      const rule = await response.json()
      set(state => ({ rules: [...state.rules, rule] }))
      return rule
    } catch (error) {
      set({ error: error.message })
      throw error
    }
  },
  
  // Update rule
  updateRule: async (ruleId, updates) => {
    try {
      const response = await fetch(`${API_URL}/api/rules/${ruleId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      if (!response.ok) throw new Error('Failed to update rule')
      const rule = await response.json()
      set(state => ({
        rules: state.rules.map(r => r.id === ruleId ? rule : r),
      }))
      return rule
    } catch (error) {
      set({ error: error.message })
      throw error
    }
  },
  
  // Delete rule
  deleteRule: async (ruleId) => {
    try {
      const response = await fetch(`${API_URL}/api/rules/${ruleId}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('Failed to delete rule')
      set(state => ({
        rules: state.rules.filter(r => r.id !== ruleId),
      }))
    } catch (error) {
      set({ error: error.message })
      throw error
    }
  },
}))

