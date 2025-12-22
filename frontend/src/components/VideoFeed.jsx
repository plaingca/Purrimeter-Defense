import { useState, useEffect, useRef } from 'react'
import { Camera, AlertTriangle, Activity, Eye, EyeOff } from 'lucide-react'
import clsx from 'clsx'
import { API_URL, WS_URL } from '../config'

export default function VideoFeed({ camera, isAlertActive = false, showOverlay = true }) {
  const [detections, setDetections] = useState({})
  const [status, setStatus] = useState(null)
  const [connected, setConnected] = useState(false)
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [showMasks, setShowMasks] = useState(true)  // Toggle for mask overlay
  const imgRef = useRef(null)
  const wsRef = useRef(null)
  
  useEffect(() => {
    if (!camera?.id) return
    
    // Reset state when camera changes
    setImageLoaded(false)
    setImageError(false)
    
    // Use MJPEG stream - separate endpoints for with/without overlay
    const mjpegUrl = showMasks 
      ? `${API_URL}/api/streams/${camera.id}/mjpeg_overlay`
      : `${API_URL}/api/streams/${camera.id}/mjpeg`
    if (imgRef.current) {
      imgRef.current.src = mjpegUrl
    }
    
    // Connect WebSocket for detection count updates
    const ws = new WebSocket(`${WS_URL}/api/streams/${camera.id}/ws`)
    wsRef.current = ws
    
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)
    
    ws.onmessage = (event) => {
      // Binary data is frame (handled by MJPEG)
      if (event.data instanceof Blob) return
      
      // JSON data is detection/status update
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'detection_update') {
          setDetections(data.detections || {})
          setStatus(data.status)
        }
      } catch (e) {
        console.error('WebSocket parse error:', e)
      }
    }
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [camera?.id, showMasks])
  
  const allDetections = Object.values(detections).flat()
  
  // Show placeholder only when image hasn't loaded or errored
  const showPlaceholder = !imageLoaded || imageError
  
  // Toggle mask overlay
  const toggleMasks = () => {
    setShowMasks(!showMasks)
    setImageLoaded(false)  // Reset to show loading state briefly
  }
  
  return (
    <div className={clsx(
      "video-feed relative group",
      isAlertActive && "alert-active"
    )}>
      {/* Video stream */}
      <div className="aspect-video bg-midnight-950 relative overflow-hidden">
        <img
          ref={imgRef}
          alt={`${camera?.name} feed`}
          className={clsx(
            "w-full h-full object-contain relative z-10",
            !imageLoaded && "opacity-0"
          )}
          onLoad={() => setImageLoaded(true)}
          onError={() => {
            setImageError(true)
            setImageLoaded(false)
          }}
        />
        
        {/* Placeholder when no stream - behind the image */}
        {showPlaceholder && (
          <div className="absolute inset-0 flex items-center justify-center text-gray-600 z-0">
            <div className="text-center">
              <Camera className="w-16 h-16 mx-auto mb-2 opacity-30" />
              <p className="text-sm">{imageError ? 'Stream unavailable' : 'Connecting...'}</p>
            </div>
          </div>
        )}
        
        {/* Mask toggle button */}
        {showOverlay && (
          <button
            onClick={toggleMasks}
            className={clsx(
              "absolute top-4 left-4 z-30 p-2 rounded-lg transition-colors",
              showMasks 
                ? "bg-purrple-500 text-white" 
                : "bg-midnight-800/80 text-gray-400 hover:text-white"
            )}
            title={showMasks ? "Hide detection masks" : "Show detection masks"}
          >
            {showMasks ? <Eye className="w-5 h-5" /> : <EyeOff className="w-5 h-5" />}
          </button>
        )}
        
        {/* Alert indicator */}
        {isAlertActive && (
          <div className="absolute top-4 right-4 z-30">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-alert-red rounded-full animate-pulse">
              <AlertTriangle className="w-4 h-4" />
              <span className="text-sm font-bold">ALERT</span>
            </div>
          </div>
        )}
      </div>
      
      {/* Camera info bar */}
      <div className="bg-midnight-800/90 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Camera className="w-4 h-4 text-purrple-400" />
          <span className="font-medium">{camera?.name || 'Camera'}</span>
        </div>
        
        <div className="flex items-center gap-4 text-sm text-gray-400">
          {/* Detection count */}
          {allDetections.length > 0 && (
            <span className="flex items-center gap-1 text-purrple-400">
              <Activity className="w-4 h-4" />
              {allDetections.length} detected
            </span>
          )}
          
          {/* Mask indicator */}
          {showMasks && (
            <span className="text-purrple-400 text-xs">
              Masks On
            </span>
          )}
          
          {/* Connection status */}
          <div className="flex items-center gap-1">
            <div className={clsx(
              "w-2 h-2 rounded-full",
              connected ? "bg-alert-green" : "bg-alert-red"
            )} />
            <span>{connected ? 'Live' : 'Offline'}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
