import { useState, useEffect, useRef, useCallback } from 'react'
import { Camera, Play, Pause, Sparkles, AlertTriangle, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import { API_URL } from '../config'

/**
 * DetectionPreview - Live SAM3 detection visualization
 * Shows camera feed with detection masks overlaid in real-time
 */
export default function DetectionPreview({ 
  camera, 
  prompts = [],
  confidence = 0.5,
  className = '',
}) {
  const [isStreaming, setIsStreaming] = useState(false)
  const [detections, setDetections] = useState({})
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const imgRef = useRef(null)
  const streamIntervalRef = useRef(null)

  // Build stream URL with prompts
  const getStreamUrl = useCallback(() => {
    if (!camera?.id || prompts.length === 0) return null
    const promptsParam = encodeURIComponent(prompts.join(','))
    return `${API_URL}/api/detection/preview/${camera.id}/stream?prompts=${promptsParam}&confidence=${confidence}`
  }, [camera?.id, prompts, confidence])

  // Start streaming
  const startStream = useCallback(() => {
    const url = getStreamUrl()
    if (!url || !imgRef.current) return

    setIsStreaming(true)
    setError(null)
    imgRef.current.src = url
  }, [getStreamUrl])

  // Stop streaming
  const stopStream = useCallback(() => {
    setIsStreaming(false)
    if (imgRef.current) {
      imgRef.current.src = ''
    }
  }, [])

  // Run a single detection
  const runDetection = useCallback(async () => {
    if (!camera?.id || prompts.length === 0) return

    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_URL}/api/detection/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          camera_id: camera.id,
          prompts: prompts,
          confidence_threshold: confidence,
        }),
      })

      if (!response.ok) throw new Error('Detection failed')

      const data = await response.json()
      setDetections(data.detections || {})

      // Show visualization
      if (data.visualization_base64 && imgRef.current) {
        imgRef.current.src = `data:image/jpeg;base64,${data.visualization_base64}`
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }, [camera?.id, prompts, confidence])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (streamIntervalRef.current) {
        clearInterval(streamIntervalRef.current)
      }
    }
  }, [])

  const totalDetections = Object.values(detections).flat().length

  return (
    <div className={clsx("detection-preview bg-midnight-900 rounded-xl overflow-hidden border border-midnight-700", className)}>
      {/* Header */}
      <div className="bg-midnight-800 px-4 py-3 flex items-center justify-between border-b border-midnight-700">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purrple-500/20 rounded-lg">
            <Sparkles className="w-5 h-5 text-purrple-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white">SAM3 Detection Preview</h3>
            <p className="text-xs text-gray-400">
              {prompts.length > 0 
                ? `Detecting: ${prompts.join(', ')}`
                : 'Add detection prompts to preview'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Detection count */}
          {totalDetections > 0 && (
            <span className="px-3 py-1 bg-alert-green/20 text-alert-green rounded-full text-sm font-medium">
              {totalDetections} found
            </span>
          )}

          {/* Controls */}
          <button
            onClick={runDetection}
            disabled={isLoading || prompts.length === 0}
            className={clsx(
              "p-2 rounded-lg transition-colors",
              isLoading 
                ? "bg-midnight-700 text-gray-500 cursor-not-allowed"
                : "bg-midnight-700 hover:bg-midnight-600 text-white"
            )}
            title="Run single detection"
          >
            <RefreshCw className={clsx("w-5 h-5", isLoading && "animate-spin")} />
          </button>

          <button
            onClick={isStreaming ? stopStream : startStream}
            disabled={prompts.length === 0}
            className={clsx(
              "p-2 rounded-lg transition-colors",
              prompts.length === 0
                ? "bg-midnight-700 text-gray-500 cursor-not-allowed"
                : isStreaming
                  ? "bg-alert-red hover:bg-alert-red/80 text-white"
                  : "bg-purrple-500 hover:bg-purrple-600 text-white"
            )}
            title={isStreaming ? "Stop stream" : "Start live detection"}
          >
            {isStreaming ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Video area */}
      <div className="aspect-video bg-midnight-950 relative">
        <img
          ref={imgRef}
          alt="Detection preview"
          className="w-full h-full object-contain"
          onError={() => setError('Stream unavailable')}
          onLoad={() => setError(null)}
        />

        {/* Placeholder when not streaming */}
        {!isStreaming && !imgRef.current?.src && (
          <div className="absolute inset-0 flex items-center justify-center text-gray-600">
            <div className="text-center">
              <Camera className="w-16 h-16 mx-auto mb-3 opacity-30" />
              <p className="text-sm text-gray-400 mb-2">
                {prompts.length === 0 
                  ? 'Add prompts to see detections'
                  : 'Click play to start live detection'}
              </p>
              {prompts.length > 0 && (
                <p className="text-xs text-gray-500">
                  Or click refresh for a single frame
                </p>
              )}
            </div>
          </div>
        )}

        {/* Loading overlay */}
        {isLoading && (
          <div className="absolute inset-0 bg-midnight-950/80 flex items-center justify-center">
            <div className="text-center">
              <Sparkles className="w-12 h-12 mx-auto mb-3 text-purrple-400 animate-pulse" />
              <p className="text-sm text-gray-300">Running SAM3 detection...</p>
            </div>
          </div>
        )}

        {/* Error overlay */}
        {error && (
          <div className="absolute inset-0 bg-midnight-950/80 flex items-center justify-center">
            <div className="text-center text-alert-red">
              <AlertTriangle className="w-12 h-12 mx-auto mb-3" />
              <p className="text-sm">{error}</p>
            </div>
          </div>
        )}

        {/* Streaming indicator */}
        {isStreaming && (
          <div className="absolute top-4 left-4">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-alert-red rounded-full">
              <span className="w-2 h-2 bg-white rounded-full animate-pulse" />
              <span className="text-sm font-medium">LIVE</span>
            </div>
          </div>
        )}
      </div>

      {/* Detection results */}
      {totalDetections > 0 && (
        <div className="p-4 border-t border-midnight-700">
          <h4 className="text-sm font-medium text-gray-400 mb-2">Detection Results</h4>
          <div className="flex flex-wrap gap-2">
            {Object.entries(detections).map(([label, dets]) => (
              dets.map((det, i) => (
                <div
                  key={`${label}-${i}`}
                  className="px-3 py-1.5 bg-purrple-500/20 border border-purrple-500/30 rounded-lg text-sm"
                >
                  <span className="text-purrple-300">{det.label}</span>
                  <span className="text-gray-400 ml-2">{Math.round(det.confidence * 100)}%</span>
                </div>
              ))
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

