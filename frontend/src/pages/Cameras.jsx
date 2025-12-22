import { useEffect, useState } from 'react'
import { 
  Camera, 
  Plus, 
  Edit2, 
  Trash2, 
  Power, 
  PowerOff,
  RefreshCw,
  X,
  Check
} from 'lucide-react'
import { useCameraStore } from '../stores/cameraStore'
import VideoFeed from '../components/VideoFeed'
import clsx from 'clsx'

export default function Cameras() {
  const { cameras, loading, fetchCameras, addCamera, updateCamera, deleteCamera } = useCameraStore()
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingCamera, setEditingCamera] = useState(null)
  
  useEffect(() => {
    fetchCameras()
  }, [])
  
  const handleDelete = async (camera) => {
    if (confirm(`Are you sure you want to delete "${camera.name}"?`)) {
      await deleteCamera(camera.id)
    }
  }
  
  const handleToggleEnabled = async (camera) => {
    await updateCamera(camera.id, { enabled: !camera.enabled })
  }
  
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Camera className="w-8 h-8 text-purrple-400" />
            Camera Sources
          </h1>
          <p className="text-gray-400 mt-1">
            Manage your RTSP camera streams for cat detection
          </p>
        </div>
        
        <button 
          onClick={() => setShowAddModal(true)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="w-5 h-5" />
          Add Camera
        </button>
      </div>
      
      {/* Camera grid */}
      {cameras.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <Camera className="w-16 h-16 mx-auto mb-4 text-gray-600" />
          <h3 className="text-xl font-bold mb-2">No cameras configured</h3>
          <p className="text-gray-500 mb-6">
            Add your first RTSP camera to start monitoring for mischievous kitties!
          </p>
          <button 
            onClick={() => setShowAddModal(true)}
            className="btn-primary"
          >
            Add Your First Camera
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {cameras.map(camera => (
            <CameraCard 
              key={camera.id}
              camera={camera}
              onEdit={() => setEditingCamera(camera)}
              onDelete={() => handleDelete(camera)}
              onToggle={() => handleToggleEnabled(camera)}
            />
          ))}
        </div>
      )}
      
      {/* Add/Edit Modal */}
      {(showAddModal || editingCamera) && (
        <CameraModal
          camera={editingCamera}
          onClose={() => {
            setShowAddModal(false)
            setEditingCamera(null)
          }}
          onSave={async (data) => {
            if (editingCamera) {
              await updateCamera(editingCamera.id, data)
            } else {
              await addCamera(data)
            }
            setShowAddModal(false)
            setEditingCamera(null)
          }}
        />
      )}
    </div>
  )
}

function CameraCard({ camera, onEdit, onDelete, onToggle }) {
  return (
    <div className={clsx(
      "glass-card overflow-hidden",
      !camera.enabled && "opacity-60"
    )}>
      {/* Video preview */}
      <div className="relative">
        {camera.enabled ? (
          <VideoFeed camera={camera} showOverlay={false} />
        ) : (
          <div className="aspect-video bg-midnight-950 flex items-center justify-center">
            <div className="text-center text-gray-600">
              <PowerOff className="w-12 h-12 mx-auto mb-2" />
              <p>Camera disabled</p>
            </div>
          </div>
        )}
      </div>
      
      {/* Camera info */}
      <div className="p-4 border-t border-midnight-700">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-lg font-bold">{camera.name}</h3>
            <p className="text-sm text-gray-500 font-mono truncate max-w-xs">
              {camera.rtsp_url}
            </p>
          </div>
          
          <button
            onClick={onToggle}
            className={clsx(
              "p-2 rounded-lg transition-colors",
              camera.enabled 
                ? "bg-alert-green/20 text-alert-green hover:bg-alert-green/30"
                : "bg-gray-700/50 text-gray-400 hover:bg-gray-600/50"
            )}
          >
            {camera.enabled ? <Power className="w-5 h-5" /> : <PowerOff className="w-5 h-5" />}
          </button>
        </div>
        
        <div className="flex items-center gap-4 text-sm text-gray-400 mb-4">
          <span>{camera.width}x{camera.height}</span>
          <span>{camera.fps} FPS</span>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={onEdit}
            className="btn-secondary flex-1 flex items-center justify-center gap-2 py-2"
          >
            <Edit2 className="w-4 h-4" />
            Edit
          </button>
          <button
            onClick={onDelete}
            className="btn-danger flex-1 flex items-center justify-center gap-2 py-2"
          >
            <Trash2 className="w-4 h-4" />
            Delete
          </button>
        </div>
      </div>
    </div>
  )
}

function CameraModal({ camera, onClose, onSave }) {
  const [formData, setFormData] = useState({
    name: camera?.name || '',
    rtsp_url: camera?.rtsp_url || '',
    fps: camera?.fps || 30,
    width: camera?.width || 1920,
    height: camera?.height || 1080,
    enabled: camera?.enabled ?? true,
  })
  const [saving, setSaving] = useState(false)
  
  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await onSave(formData)
    } finally {
      setSaving(false)
    }
  }
  
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="glass-card w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold">
            {camera ? 'Edit Camera' : 'Add Camera'}
          </h2>
          <button 
            onClick={onClose}
            className="p-2 hover:bg-midnight-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Camera Name
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={e => setFormData({ ...formData, name: e.target.value })}
              placeholder="Kitchen Camera"
              className="input-field"
              required
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              RTSP URL
            </label>
            <input
              type="text"
              value={formData.rtsp_url}
              onChange={e => setFormData({ ...formData, rtsp_url: e.target.value })}
              placeholder="rtsp://192.168.1.100:554/stream"
              className="input-field font-mono text-sm"
              required
            />
            <p className="text-xs text-gray-500 mt-1">
              Example: rtsp://username:password@192.168.1.100:554/stream1
            </p>
          </div>
          
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Width
              </label>
              <input
                type="number"
                value={formData.width}
                onChange={e => setFormData({ ...formData, width: parseInt(e.target.value) })}
                className="input-field"
                min={320}
                max={3840}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Height
              </label>
              <input
                type="number"
                value={formData.height}
                onChange={e => setFormData({ ...formData, height: parseInt(e.target.value) })}
                className="input-field"
                min={240}
                max={2160}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                FPS
              </label>
              <input
                type="number"
                value={formData.fps}
                onChange={e => setFormData({ ...formData, fps: parseInt(e.target.value) })}
                className="input-field"
                min={1}
                max={60}
              />
            </div>
          </div>
          
          <div className="flex items-center gap-3 p-4 bg-midnight-800 rounded-lg">
            <input
              type="checkbox"
              id="enabled"
              checked={formData.enabled}
              onChange={e => setFormData({ ...formData, enabled: e.target.checked })}
              className="w-5 h-5 rounded border-gray-600 text-purrple-500 focus:ring-purrple-500"
            />
            <label htmlFor="enabled" className="font-medium">
              Enable camera on save
            </label>
          </div>
          
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary flex-1"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="btn-primary flex-1 flex items-center justify-center gap-2"
            >
              {saving ? (
                <RefreshCw className="w-5 h-5 animate-spin" />
              ) : (
                <Check className="w-5 h-5" />
              )}
              {camera ? 'Save Changes' : 'Add Camera'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

