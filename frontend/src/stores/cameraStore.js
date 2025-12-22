import { create } from 'zustand'
import { API_URL } from '../config'

export const useCameraStore = create((set, get) => ({
  cameras: [],
  loading: false,
  error: null,
  
  // Fetch all cameras
  fetchCameras: async () => {
    set({ loading: true, error: null })
    try {
      const response = await fetch(`${API_URL}/api/cameras/`)
      if (!response.ok) throw new Error('Failed to fetch cameras')
      const cameras = await response.json()
      set({ cameras, loading: false })
    } catch (error) {
      set({ error: error.message, loading: false })
    }
  },
  
  // Add camera
  addCamera: async (cameraData) => {
    try {
      const response = await fetch(`${API_URL}/api/cameras/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cameraData),
      })
      if (!response.ok) throw new Error('Failed to add camera')
      const camera = await response.json()
      set(state => ({ cameras: [...state.cameras, camera] }))
      return camera
    } catch (error) {
      set({ error: error.message })
      throw error
    }
  },
  
  // Update camera
  updateCamera: async (cameraId, updates) => {
    try {
      const response = await fetch(`${API_URL}/api/cameras/${cameraId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      if (!response.ok) throw new Error('Failed to update camera')
      const camera = await response.json()
      set(state => ({
        cameras: state.cameras.map(c => c.id === cameraId ? camera : c),
      }))
      return camera
    } catch (error) {
      set({ error: error.message })
      throw error
    }
  },
  
  // Delete camera
  deleteCamera: async (cameraId) => {
    try {
      const response = await fetch(`${API_URL}/api/cameras/${cameraId}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('Failed to delete camera')
      set(state => ({
        cameras: state.cameras.filter(c => c.id !== cameraId),
      }))
    } catch (error) {
      set({ error: error.message })
      throw error
    }
  },
  
  // Get camera status
  getCameraStatus: async (cameraId) => {
    try {
      const response = await fetch(`${API_URL}/api/cameras/${cameraId}/status`)
      if (!response.ok) throw new Error('Failed to get camera status')
      return await response.json()
    } catch (error) {
      console.error('Camera status error:', error)
      return null
    }
  },
}))

