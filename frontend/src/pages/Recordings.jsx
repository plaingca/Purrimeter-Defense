import { useEffect, useState } from 'react'
import { 
  Video, 
  Play, 
  Trash2, 
  Download,
  Clock,
  HardDrive,
  Calendar,
  ChevronLeft,
  ChevronRight,
  X
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'
import { API_URL } from '../config'

export default function Recordings() {
  const [recordings, setRecordings] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [selectedRecording, setSelectedRecording] = useState(null)
  
  const pageSize = 12
  
  useEffect(() => {
    fetchRecordings()
    fetchStats()
  }, [page])
  
  const fetchRecordings = async () => {
    setLoading(true)
    try {
      const response = await fetch(
        `${API_URL}/api/recordings/?limit=${pageSize}&offset=${page * pageSize}`
      )
      const data = await response.json()
      setRecordings(data)
    } catch (error) {
      console.error('Failed to fetch recordings:', error)
    } finally {
      setLoading(false)
    }
  }
  
  const fetchStats = async () => {
    try {
      const response = await fetch(`${API_URL}/api/recordings/stats/summary`)
      const data = await response.json()
      setStats(data)
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    }
  }
  
  const handleDelete = async (recording) => {
    if (!confirm(`Delete recording "${recording.filename}"?`)) return
    
    try {
      await fetch(`${API_URL}/api/recordings/${recording.id}`, {
        method: 'DELETE',
      })
      setRecordings(recordings.filter(r => r.id !== recording.id))
      fetchStats()
    } catch (error) {
      console.error('Failed to delete recording:', error)
    }
  }
  
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Video className="w-8 h-8 text-purrple-400" />
            Recordings
          </h1>
          <p className="text-gray-400 mt-1">
            Alert recordings from your cat defense system
          </p>
        </div>
      </div>
      
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="glass-card p-4 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-purrple-500/20 flex items-center justify-center">
              <Video className="w-6 h-6 text-purrple-400" />
            </div>
            <div>
              <div className="text-2xl font-bold">{stats.total_recordings}</div>
              <div className="text-sm text-gray-500">Total Recordings</div>
            </div>
          </div>
          
          <div className="glass-card p-4 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-catblue-500/20 flex items-center justify-center">
              <Clock className="w-6 h-6 text-catblue-400" />
            </div>
            <div>
              <div className="text-2xl font-bold">
                {formatDuration(stats.total_duration_seconds)}
              </div>
              <div className="text-sm text-gray-500">Total Duration</div>
            </div>
          </div>
          
          <div className="glass-card p-4 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-purple-500/20 flex items-center justify-center">
              <HardDrive className="w-6 h-6 text-purple-400" />
            </div>
            <div>
              <div className="text-2xl font-bold">{stats.total_size_mb} MB</div>
              <div className="text-sm text-gray-500">Storage Used</div>
            </div>
          </div>
        </div>
      )}
      
      {/* Recordings grid */}
      {loading ? (
        <div className="glass-card p-12 text-center">
          <div className="animate-pulse">
            <Video className="w-16 h-16 mx-auto mb-4 text-gray-600" />
            <p className="text-gray-500">Loading recordings...</p>
          </div>
        </div>
      ) : recordings.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <Video className="w-16 h-16 mx-auto mb-4 text-gray-600" />
          <h3 className="text-xl font-bold mb-2">No recordings yet</h3>
          <p className="text-gray-500">
            Recordings will appear here when alerts are triggered
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {recordings.map(recording => (
              <RecordingCard
                key={recording.id}
                recording={recording}
                onPlay={() => setSelectedRecording(recording)}
                onDelete={() => handleDelete(recording)}
              />
            ))}
          </div>
          
          {/* Pagination */}
          <div className="flex items-center justify-center gap-4">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="btn-secondary flex items-center gap-2 disabled:opacity-50"
            >
              <ChevronLeft className="w-4 h-4" />
              Previous
            </button>
            <span className="text-gray-500">
              Page {page + 1}
            </span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={recordings.length < pageSize}
              className="btn-secondary flex items-center gap-2 disabled:opacity-50"
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </>
      )}
      
      {/* Video player modal */}
      {selectedRecording && (
        <VideoPlayerModal
          recording={selectedRecording}
          onClose={() => setSelectedRecording(null)}
        />
      )}
    </div>
  )
}

function RecordingCard({ recording, onPlay, onDelete }) {
  const thumbnailUrl = recording.thumbnail_path 
    ? `${API_URL}/recordings/${recording.thumbnail_path.split('/').pop()}`
    : null
  
  return (
    <div className="glass-card overflow-hidden group">
      {/* Thumbnail */}
      <div 
        className="aspect-video bg-midnight-950 relative cursor-pointer"
        onClick={onPlay}
      >
        {thumbnailUrl ? (
          <img 
            src={thumbnailUrl} 
            alt="Recording thumbnail"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <Video className="w-12 h-12 text-gray-700" />
          </div>
        )}
        
        {/* Play overlay */}
        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
          <div className="w-16 h-16 rounded-full bg-purrple-500/90 flex items-center justify-center">
            <Play className="w-8 h-8 ml-1" />
          </div>
        </div>
        
        {/* Duration badge */}
        {recording.duration_seconds && (
          <div className="absolute bottom-2 right-2 px-2 py-1 bg-black/70 rounded text-xs">
            {formatDuration(recording.duration_seconds)}
          </div>
        )}
      </div>
      
      {/* Info */}
      <div className="p-4">
        <div className="flex items-start justify-between mb-2">
          <div className="min-w-0 flex-1">
            <h3 className="font-medium truncate">{recording.filename}</h3>
            <p className="text-sm text-gray-500 flex items-center gap-1">
              <Calendar className="w-3 h-3" />
              {formatDistanceToNow(new Date(recording.started_at), { addSuffix: true })}
            </p>
          </div>
          
          {recording.discord_sent && (
            <span className="px-2 py-0.5 bg-indigo-500/20 text-indigo-400 text-xs rounded">
              Discord
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-2 text-sm text-gray-500 mb-4">
          {recording.file_size_bytes && (
            <span>{(recording.file_size_bytes / 1024 / 1024).toFixed(1)} MB</span>
          )}
        </div>
        
        <div className="flex gap-2">
          <button
            onClick={onPlay}
            className="btn-primary flex-1 py-2 flex items-center justify-center gap-2"
          >
            <Play className="w-4 h-4" />
            Play
          </button>
          <a
            href={`${API_URL}/api/recordings/${recording.id}/video`}
            download={recording.filename}
            className="btn-secondary py-2 px-3"
          >
            <Download className="w-4 h-4" />
          </a>
          <button
            onClick={onDelete}
            className="btn-danger py-2 px-3"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

function VideoPlayerModal({ recording, onClose }) {
  const videoUrl = `${API_URL}/api/recordings/${recording.id}/video`
  
  return (
    <div 
      className="fixed inset-0 bg-black/90 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div 
        className="relative w-full max-w-4xl"
        onClick={e => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute -top-12 right-0 p-2 text-gray-400 hover:text-white"
        >
          <X className="w-6 h-6" />
        </button>
        
        <video
          src={videoUrl}
          controls
          autoPlay
          className="w-full rounded-xl shadow-2xl"
        />
        
        <div className="mt-4 text-center">
          <h3 className="font-bold text-lg">{recording.filename}</h3>
          <p className="text-gray-500">
            {new Date(recording.started_at).toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  )
}

function formatDuration(seconds) {
  if (!seconds) return '0:00'
  
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  
  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

