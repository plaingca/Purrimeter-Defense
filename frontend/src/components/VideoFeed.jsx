import { useState, useEffect, useRef, useCallback } from 'react'
import { Camera, AlertTriangle, Activity, Eye, EyeOff, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import { API_URL, WS_URL } from '../config'

// WebSocket reconnection configuration
const WS_RECONNECT_CONFIG = {
  initialDelay: 1000,      // 1 second
  maxDelay: 30000,         // 30 seconds max
  backoffFactor: 1.5,      // Exponential backoff multiplier
  maxAttempts: Infinity,   // Keep trying forever
}

// MJPEG stream retry configuration
const MJPEG_RETRY_CONFIG = {
  initialDelay: 2000,      // 2 seconds
  maxDelay: 30000,         // 30 seconds max
  backoffFactor: 1.5,      // Exponential backoff multiplier
}

export default function VideoFeed({ camera, isAlertActive = false, showOverlay = true }) {
  const [detections, setDetections] = useState({})
  const [status, setStatus] = useState(null)
  const [connected, setConnected] = useState(false)
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [showMasks, setShowMasks] = useState(true)  // Toggle for mask overlay
  const [wsReconnecting, setWsReconnecting] = useState(false)
  const [streamReconnecting, setStreamReconnecting] = useState(false)
  const [mjpegRetrying, setMjpegRetrying] = useState(false)
  const imgRef = useRef(null)
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)
  const shouldReconnectRef = useRef(true)
  const mjpegRetryTimeoutRef = useRef(null)
  const mjpegRetryAttemptsRef = useRef(0)
  
  // Calculate reconnect delay with exponential backoff
  const getReconnectDelay = useCallback(() => {
    const attempt = reconnectAttemptsRef.current
    const delay = Math.min(
      WS_RECONNECT_CONFIG.initialDelay * Math.pow(WS_RECONNECT_CONFIG.backoffFactor, attempt),
      WS_RECONNECT_CONFIG.maxDelay
    )
    return delay
  }, [])
  
  // Calculate MJPEG retry delay with exponential backoff
  const getMjpegRetryDelay = useCallback(() => {
    const attempt = mjpegRetryAttemptsRef.current
    const delay = Math.min(
      MJPEG_RETRY_CONFIG.initialDelay * Math.pow(MJPEG_RETRY_CONFIG.backoffFactor, attempt),
      MJPEG_RETRY_CONFIG.maxDelay
    )
    return delay
  }, [])
  
  // Retry loading MJPEG stream
  const retryMjpegStream = useCallback(() => {
    if (!camera?.id || !shouldReconnectRef.current) return
    
    const mjpegUrl = showMasks 
      ? `${API_URL}/api/streams/${camera.id}/mjpeg_overlay`
      : `${API_URL}/api/streams/${camera.id}/mjpeg`
    
    // Add cache-busting parameter to force reload
    const urlWithCacheBust = `${mjpegUrl}?t=${Date.now()}`
    
    if (imgRef.current) {
      console.log(`🐱 Retrying MJPEG stream for camera ${camera.id} (attempt ${mjpegRetryAttemptsRef.current + 1})`)
      imgRef.current.src = urlWithCacheBust
    }
  }, [camera?.id, showMasks])
  
  // Handle MJPEG stream error with retry
  const handleImageError = useCallback(() => {
    setImageError(true)
    setImageLoaded(false)
    
    if (shouldReconnectRef.current) {
      const delay = getMjpegRetryDelay()
      mjpegRetryAttemptsRef.current += 1
      setMjpegRetrying(true)
      
      console.log(`🐱 MJPEG stream error, retrying in ${delay}ms (attempt ${mjpegRetryAttemptsRef.current})`)
      
      // Clear any pending retry
      if (mjpegRetryTimeoutRef.current) {
        clearTimeout(mjpegRetryTimeoutRef.current)
      }
      
      mjpegRetryTimeoutRef.current = setTimeout(() => {
        setMjpegRetrying(false)
        retryMjpegStream()
      }, delay)
    }
  }, [getMjpegRetryDelay, retryMjpegStream])
  
  // Handle successful MJPEG load
  const handleImageLoad = useCallback(() => {
    setImageLoaded(true)
    setImageError(false)
    setMjpegRetrying(false)
    mjpegRetryAttemptsRef.current = 0
  }, [])
  
  // Connect WebSocket with reconnection support
  const connectWebSocket = useCallback(() => {
    if (!camera?.id || !shouldReconnectRef.current) return
    
    // Clear any pending reconnection
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    
    const ws = new WebSocket(`${WS_URL}/api/streams/${camera.id}/ws`)
    wsRef.current = ws
    
    ws.onopen = () => {
      console.log(`🐱 VideoFeed WebSocket connected for camera ${camera.id}`)
      setConnected(true)
      setWsReconnecting(false)
      reconnectAttemptsRef.current = 0
    }
    
    ws.onclose = (event) => {
      console.log(`🐱 VideoFeed WebSocket closed for camera ${camera.id}`, event.code, event.reason)
      setConnected(false)
      wsRef.current = null
      
      // Attempt to reconnect if we should
      if (shouldReconnectRef.current && reconnectAttemptsRef.current < WS_RECONNECT_CONFIG.maxAttempts) {
        const delay = getReconnectDelay()
        reconnectAttemptsRef.current += 1
        setWsReconnecting(true)
        
        console.log(`🐱 Reconnecting WebSocket in ${delay}ms (attempt ${reconnectAttemptsRef.current})`)
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, delay)
      }
    }
    
    ws.onerror = (error) => {
      console.error(`🐱 VideoFeed WebSocket error for camera ${camera.id}:`, error)
      setConnected(false)
    }
    
    ws.onmessage = (event) => {
      // Binary data is frame (handled by MJPEG)
      if (event.data instanceof Blob) return
      
      // JSON data is detection/status update
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'detection_update') {
          setDetections(data.detections || {})
          setStatus(data.status)
          
          // Check if backend stream is reconnecting
          const streamStatus = data.status?.stream_status
          setStreamReconnecting(streamStatus === 'reconnecting')
        }
      } catch (e) {
        console.error('WebSocket parse error:', e)
      }
    }
  }, [camera?.id, getReconnectDelay])
  
  useEffect(() => {
    if (!camera?.id) return
    
    // Reset state when camera changes
    setImageLoaded(false)
    setImageError(false)
    setMjpegRetrying(false)
    shouldReconnectRef.current = true
    reconnectAttemptsRef.current = 0
    mjpegRetryAttemptsRef.current = 0
    
    // Use MJPEG stream - separate endpoints for with/without overlay
    const mjpegUrl = showMasks 
      ? `${API_URL}/api/streams/${camera.id}/mjpeg_overlay`
      : `${API_URL}/api/streams/${camera.id}/mjpeg`
    if (imgRef.current) {
      imgRef.current.src = mjpegUrl
    }
    
    // Connect WebSocket for detection count updates
    connectWebSocket()
    
    return () => {
      // Cleanup: stop reconnection attempts and close WebSocket
      shouldReconnectRef.current = false
      
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      if (mjpegRetryTimeoutRef.current) {
        clearTimeout(mjpegRetryTimeoutRef.current)
        mjpegRetryTimeoutRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [camera?.id, showMasks, connectWebSocket])
  
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
          onLoad={handleImageLoad}
          onError={handleImageError}
        />
        
        {/* Placeholder when no stream - behind the image */}
        {showPlaceholder && (
          <div className="absolute inset-0 flex items-center justify-center text-gray-600 z-0">
            <div className="text-center">
              {streamReconnecting ? (
                <>
                  <RefreshCw className="w-16 h-16 mx-auto mb-2 opacity-50 animate-spin" />
                  <p className="text-sm text-yellow-500">Reconnecting to camera...</p>
                </>
              ) : mjpegRetrying ? (
                <>
                  <RefreshCw className="w-16 h-16 mx-auto mb-2 opacity-50 animate-spin" />
                  <p className="text-sm text-yellow-500">Retrying stream...</p>
                </>
              ) : (
                <>
                  <Camera className="w-16 h-16 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">{imageError ? 'Stream unavailable' : 'Connecting...'}</p>
                </>
              )}
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
            {streamReconnecting ? (
              <>
                <RefreshCw className="w-3 h-3 text-yellow-500 animate-spin" />
                <span className="text-yellow-500">Camera Reconnecting</span>
              </>
            ) : wsReconnecting ? (
              <>
                <RefreshCw className="w-3 h-3 text-yellow-500 animate-spin" />
                <span className="text-yellow-500">Reconnecting</span>
              </>
            ) : (
              <>
                <div className={clsx(
                  "w-2 h-2 rounded-full",
                  connected ? "bg-alert-green" : "bg-alert-red"
                )} />
                <span>{connected ? 'Live' : 'Offline'}</span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
