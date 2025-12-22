import { useEffect, useState, useMemo } from 'react'
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
  X,
  Filter,
  AlertTriangle,
  Camera,
  Shield,
  TrendingUp,
  Eye,
  Search,
  BarChart3,
  Cat
} from 'lucide-react'
import { format, formatDistanceToNow, subDays, startOfDay, endOfDay, parseISO } from 'date-fns'
import clsx from 'clsx'
import { API_URL } from '../config'
import { useCameraStore } from '../stores/cameraStore'
import { useRuleStore } from '../stores/ruleStore'

export default function Recordings() {
  const { cameras, fetchCameras } = useCameraStore()
  const { rules, fetchRules } = useRuleStore()
  
  const [events, setEvents] = useState([])
  const [recordings, setRecordings] = useState([])
  const [stats, setStats] = useState(null)
  const [dailySummary, setDailySummary] = useState([])
  const [loading, setLoading] = useState(true)
  const [totalCount, setTotalCount] = useState(0)
  const [totalRecordingsCount, setTotalRecordingsCount] = useState(0)
  const [page, setPage] = useState(0)
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [selectedRecording, setSelectedRecording] = useState(null)
  
  // View mode: 'events' or 'recordings'
  const [viewMode, setViewMode] = useState('events')
  
  // Filters
  const [dateRange, setDateRange] = useState(7) // days
  const [selectedCamera, setSelectedCamera] = useState('')
  const [selectedRule, setSelectedRule] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  
  const pageSize = 20
  
  useEffect(() => {
    fetchCameras()
    fetchRules()
  }, [])
  
  useEffect(() => {
    fetchEvents()
    fetchRecordings()
    fetchStats()
    fetchDailySummary()
  }, [page, dateRange, selectedCamera, selectedRule, viewMode])
  
  const fetchEvents = async () => {
    if (viewMode !== 'events') return
    setLoading(true)
    try {
      const params = new URLSearchParams({
        limit: pageSize.toString(),
        offset: (page * pageSize).toString(),
        date_from: subDays(new Date(), dateRange).toISOString(),
        date_to: new Date().toISOString(),
      })
      
      if (selectedCamera) params.append('camera_id', selectedCamera)
      if (selectedRule) params.append('rule_id', selectedRule)
      
      const response = await fetch(`${API_URL}/api/alerts/events?${params}`)
      const data = await response.json()
      setEvents(data.events || [])
      setTotalCount(data.total_count || 0)
    } catch (error) {
      console.error('Failed to fetch events:', error)
    } finally {
      setLoading(false)
    }
  }
  
  const fetchRecordings = async () => {
    if (viewMode !== 'recordings') return
    setLoading(true)
    try {
      const params = new URLSearchParams({
        limit: pageSize.toString(),
        offset: (page * pageSize).toString(),
      })
      
      if (selectedCamera) params.append('camera_id', selectedCamera)
      
      const response = await fetch(`${API_URL}/api/recordings/?${params}`)
      const data = await response.json()
      setRecordings(data || [])
      setTotalRecordingsCount(data?.length || 0)
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
  
  const fetchDailySummary = async () => {
    try {
      const params = new URLSearchParams({ days: dateRange.toString() })
      if (selectedCamera) params.append('camera_id', selectedCamera)
      
      const response = await fetch(`${API_URL}/api/alerts/events/daily-summary?${params}`)
      const data = await response.json()
      setDailySummary(data.summary || [])
    } catch (error) {
      console.error('Failed to fetch daily summary:', error)
    }
  }
  
  const handleDelete = async (event) => {
    if (!event.recording) return
    if (!confirm(`Delete recording for this event?`)) return
    
    try {
      await fetch(`${API_URL}/api/recordings/${event.recording.id}`, {
        method: 'DELETE',
      })
      // Refresh events
      fetchEvents()
      fetchStats()
    } catch (error) {
      console.error('Failed to delete recording:', error)
    }
  }
  
  const handleDeleteRecording = async (recording) => {
    if (!confirm(`Delete recording "${recording.filename}"?`)) return
    
    try {
      await fetch(`${API_URL}/api/recordings/${recording.id}`, {
        method: 'DELETE',
      })
      // Refresh recordings
      fetchRecordings()
      fetchStats()
    } catch (error) {
      console.error('Failed to delete recording:', error)
    }
  }
  
  // Filter events by search query
  const filteredEvents = useMemo(() => {
    if (!searchQuery.trim()) return events
    const query = searchQuery.toLowerCase()
    return events.filter(event => 
      event.rule_name?.toLowerCase().includes(query) ||
      event.camera_name?.toLowerCase().includes(query) ||
      event.primary_target?.toLowerCase().includes(query) ||
      event.message?.toLowerCase().includes(query)
    )
  }, [events, searchQuery])
  
  // Calculate max for chart scaling
  const maxDailyCount = Math.max(...dailySummary.map(d => d.count), 1)
  
  const totalPages = Math.ceil(totalCount / pageSize)
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purrple-500 to-purrple-700 flex items-center justify-center">
              {viewMode === 'events' ? <AlertTriangle className="w-5 h-5" /> : <Video className="w-5 h-5" />}
            </div>
            {viewMode === 'events' ? 'Event Explorer' : 'Recordings'}
          </h1>
          <p className="text-gray-400 mt-1">
            {viewMode === 'events' 
              ? 'Track detection events and recordings over time'
              : 'Browse all recorded videos'
            }
          </p>
        </div>
        
        <div className="flex items-center gap-4">
          {/* View mode toggle */}
          <div className="flex items-center bg-midnight-800 rounded-lg p-1">
            <button
              onClick={() => { setViewMode('events'); setPage(0) }}
              className={clsx(
                'px-3 py-1.5 rounded-md text-sm font-medium transition-all flex items-center gap-1.5',
                viewMode === 'events'
                  ? 'bg-purrple-500 text-white'
                  : 'text-gray-400 hover:text-white'
              )}
            >
              <AlertTriangle className="w-4 h-4" />
              Events
            </button>
            <button
              onClick={() => { setViewMode('recordings'); setPage(0) }}
              className={clsx(
                'px-3 py-1.5 rounded-md text-sm font-medium transition-all flex items-center gap-1.5',
                viewMode === 'recordings'
                  ? 'bg-purrple-500 text-white'
                  : 'text-gray-400 hover:text-white'
              )}
            >
              <Video className="w-4 h-4" />
              Recordings
            </button>
          </div>
          
          {/* Quick date range selector - only for events */}
          {viewMode === 'events' && (
            <div className="flex items-center gap-2">
              {[
                { label: '24h', value: 1 },
                { label: '7d', value: 7 },
                { label: '30d', value: 30 },
              ].map(({ label, value }) => (
                <button
                  key={value}
                  onClick={() => { setDateRange(value); setPage(0) }}
                  className={clsx(
                    'px-4 py-2 rounded-lg font-medium transition-all',
                    dateRange === value
                      ? 'bg-purrple-500 text-white'
                      : 'bg-midnight-800 text-gray-400 hover:bg-midnight-700'
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      
      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard 
          icon={AlertTriangle}
          label="Total Events"
          value={totalCount}
          color="orange"
        />
        <StatCard 
          icon={Video}
          label="Recordings"
          value={stats?.total_recordings || 0}
          color="purple"
        />
        <StatCard 
          icon={Clock}
          label="Total Duration"
          value={formatDuration(stats?.total_duration_seconds)}
          color="blue"
        />
        <StatCard 
          icon={HardDrive}
          label="Storage Used"
          value={`${stats?.total_size_mb || 0} MB`}
          color="green"
        />
      </div>
      
      {/* Activity Chart */}
      {dailySummary.length > 0 && (
        <div className="glass-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-purrple-400" />
              Event Activity
            </h3>
            <span className="text-sm text-gray-500">
              Last {dateRange} day{dateRange !== 1 ? 's' : ''}
            </span>
          </div>
          
          <div className="h-24 flex items-end gap-1">
            {dailySummary.map((day, i) => (
              <div
                key={day.date}
                className="flex-1 group relative"
                title={`${format(parseISO(day.date), 'MMM d')}: ${day.count} events`}
              >
                <div
                  className={clsx(
                    'w-full rounded-t transition-all',
                    day.count > 0 
                      ? 'bg-gradient-to-t from-purrple-600 to-purrple-400 group-hover:from-purrple-500 group-hover:to-purrple-300'
                      : 'bg-midnight-700'
                  )}
                  style={{ 
                    height: `${Math.max((day.count / maxDailyCount) * 100, 4)}%`,
                    minHeight: '4px'
                  }}
                />
                
                {/* Tooltip */}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-midnight-800 rounded text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                  {format(parseISO(day.date), 'MMM d')}: {day.count}
                </div>
              </div>
            ))}
          </div>
          
          {/* X-axis labels */}
          <div className="flex justify-between mt-2 text-xs text-gray-500">
            <span>{format(subDays(new Date(), dateRange), 'MMM d')}</span>
            <span>Today</span>
          </div>
        </div>
      )}
      
      {/* Filters */}
      <div className="glass-card p-4">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search events..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="input-field pl-10"
            />
          </div>
          
          {/* Camera filter */}
          <div className="relative">
            <Camera className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <select
              value={selectedCamera}
              onChange={(e) => { setSelectedCamera(e.target.value); setPage(0) }}
              className="input-field pl-10 pr-8 appearance-none cursor-pointer"
            >
              <option value="">All Cameras</option>
              {cameras.map(camera => (
                <option key={camera.id} value={camera.id}>{camera.name}</option>
              ))}
            </select>
          </div>
          
          {/* Rule filter */}
          <div className="relative">
            <Shield className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <select
              value={selectedRule}
              onChange={(e) => { setSelectedRule(e.target.value); setPage(0) }}
              className="input-field pl-10 pr-8 appearance-none cursor-pointer"
            >
              <option value="">All Rules</option>
              {rules.map(rule => (
                <option key={rule.id} value={rule.id}>{rule.name}</option>
              ))}
            </select>
          </div>
        </div>
      </div>
      
      {/* Content List */}
      {loading ? (
        <div className="glass-card p-12 text-center">
          <div className="animate-pulse">
            {viewMode === 'events' ? (
              <AlertTriangle className="w-16 h-16 mx-auto mb-4 text-gray-600" />
            ) : (
              <Video className="w-16 h-16 mx-auto mb-4 text-gray-600" />
            )}
            <p className="text-gray-500">Loading {viewMode}...</p>
          </div>
        </div>
      ) : viewMode === 'events' ? (
        // Events view
        filteredEvents.length === 0 ? (
          <EmptyState totalCount={totalCount} viewMode={viewMode} stats={stats} onSwitchView={() => setViewMode('recordings')} />
        ) : (
          <>
            <div className="space-y-3">
              {filteredEvents.map(event => (
                <EventCard
                  key={event.id}
                  event={event}
                  onPlay={() => setSelectedEvent(event)}
                  onDelete={() => handleDelete(event)}
                />
              ))}
            </div>
            
            {/* Pagination */}
            {totalPages > 1 && (
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
                  Page {page + 1} of {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => p + 1)}
                  disabled={page >= totalPages - 1}
                  className="btn-secondary flex items-center gap-2 disabled:opacity-50"
                >
                  Next
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </>
        )
      ) : (
        // Recordings view
        recordings.length === 0 ? (
          <EmptyState totalCount={0} viewMode={viewMode} />
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {recordings.map(recording => (
                <RecordingCard
                  key={recording.id}
                  recording={recording}
                  onPlay={() => setSelectedRecording(recording)}
                  onDelete={() => handleDeleteRecording(recording)}
                />
              ))}
            </div>
            
            {/* Pagination */}
            {recordings.length >= pageSize && (
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
            )}
          </>
        )
      )}
      
      {/* Video player modals */}
      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
      
      {selectedRecording && (
        <RecordingPlayerModal
          recording={selectedRecording}
          onClose={() => setSelectedRecording(null)}
        />
      )}
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color }) {
  const colorClasses = {
    orange: 'text-alert-orange bg-alert-orange/10',
    purple: 'text-purple-400 bg-purple-500/10',
    blue: 'text-catblue-400 bg-catblue-500/10',
    green: 'text-alert-green bg-alert-green/10',
  }
  
  return (
    <div className="glass-card p-4 flex items-center gap-4">
      <div className={clsx(
        'w-12 h-12 rounded-xl flex items-center justify-center',
        colorClasses[color]
      )}>
        <Icon className="w-6 h-6" />
      </div>
      <div>
        <div className="text-2xl font-bold">{value}</div>
        <div className="text-sm text-gray-500">{label}</div>
      </div>
    </div>
  )
}

function EventCard({ event, onPlay, onDelete }) {
  const hasRecording = !!event.recording
  const thumbnailUrl = event.recording?.thumbnail_path 
    ? `${API_URL}/recordings/${event.recording.thumbnail_path.split('/').pop()}`
    : null
  
  return (
    <div className="glass-card overflow-hidden hover:border-purrple-500/30 transition-colors">
      <div className="flex flex-col md:flex-row">
        {/* Thumbnail / Icon */}
        <div 
          className={clsx(
            'w-full md:w-48 aspect-video md:aspect-auto flex-shrink-0 bg-midnight-950 relative',
            hasRecording && 'cursor-pointer group'
          )}
          onClick={hasRecording ? onPlay : undefined}
        >
          {thumbnailUrl ? (
            <img 
              src={thumbnailUrl} 
              alt="Event thumbnail"
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              {hasRecording ? (
                <Video className="w-12 h-12 text-gray-700" />
              ) : (
                <Cat className="w-12 h-12 text-gray-700" />
              )}
            </div>
          )}
          
          {/* Play overlay */}
          {hasRecording && (
            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <div className="w-12 h-12 rounded-full bg-purrple-500/90 flex items-center justify-center">
                <Play className="w-6 h-6 ml-0.5" />
              </div>
            </div>
          )}
          
          {/* Duration badge */}
          {event.duration_seconds && (
            <div className="absolute bottom-2 right-2 px-2 py-0.5 bg-black/70 rounded text-xs">
              {formatDuration(event.duration_seconds)}
            </div>
          )}
        </div>
        
        {/* Content */}
        <div className="flex-1 p-4 flex flex-col justify-between">
          <div>
            {/* Header row */}
            <div className="flex items-start justify-between gap-4 mb-2">
              <div>
                <h3 className="font-semibold text-lg flex items-center gap-2">
                  <Shield className="w-4 h-4 text-purrple-400" />
                  {event.rule_name || 'Detection Event'}
                </h3>
                <div className="flex items-center gap-3 text-sm text-gray-500 mt-1">
                  <span className="flex items-center gap-1">
                    <Camera className="w-3 h-3" />
                    {event.camera_name || 'Unknown Camera'}
                  </span>
                  <span className="flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    {formatDistanceToNow(parseISO(event.triggered_at), { addSuffix: true })}
                  </span>
                </div>
              </div>
              
              {/* State badge */}
              <span className={clsx(
                'px-2 py-1 text-xs font-medium rounded',
                event.state === 'triggered' && 'bg-alert-red/20 text-alert-red',
                event.state === 'recording' && 'bg-alert-orange/20 text-alert-orange',
                event.state === 'cooldown' && 'bg-catblue-500/20 text-catblue-400',
                event.state === 'idle' && 'bg-gray-500/20 text-gray-400',
              )}>
                {event.state}
              </span>
            </div>
            
            {/* Detection details */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {event.primary_target && (
                <span className="px-2 py-0.5 bg-purrple-500/20 text-purrple-400 text-xs rounded">
                  {event.primary_target}
                </span>
              )}
              {event.secondary_target && (
                <>
                  <span className="text-gray-600">→</span>
                  <span className="px-2 py-0.5 bg-catblue-500/20 text-catblue-400 text-xs rounded">
                    {event.secondary_target}
                  </span>
                </>
              )}
              {event.detection_confidence && (
                <span className="text-xs text-gray-500">
                  {(event.detection_confidence * 100).toFixed(0)}% confidence
                </span>
              )}
            </div>
            
            {/* Message */}
            {event.message && (
              <p className="text-sm text-gray-400">{event.message}</p>
            )}
          </div>
          
          {/* Actions */}
          <div className="flex items-center gap-2 mt-4">
            {hasRecording ? (
              <>
                <button
                  onClick={onPlay}
                  className="btn-primary py-2 px-4 flex items-center gap-2"
                >
                  <Play className="w-4 h-4" />
                  Watch
                </button>
                <a
                  href={`${API_URL}/api/recordings/${event.recording.id}/video`}
                  download={event.recording.filename}
                  className="btn-secondary py-2 px-3"
                  title="Download"
                >
                  <Download className="w-4 h-4" />
                </a>
                <button
                  onClick={onDelete}
                  className="btn-danger py-2 px-3"
                  title="Delete recording"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </>
            ) : (
              <span className="text-sm text-gray-500 italic">
                No recording available
              </span>
            )}
            
            {event.recording?.discord_sent && (
              <span className="ml-auto px-2 py-0.5 bg-indigo-500/20 text-indigo-400 text-xs rounded">
                Sent to Discord
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function EventDetailModal({ event, onClose }) {
  const hasRecording = !!event.recording
  const videoUrl = hasRecording 
    ? `${API_URL}/api/recordings/${event.recording.id}/video`
    : null
  
  return (
    <div 
      className="fixed inset-0 bg-black/90 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div 
        className="relative w-full max-w-5xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute -top-12 right-0 p-2 text-gray-400 hover:text-white z-10"
        >
          <X className="w-6 h-6" />
        </button>
        
        <div className="glass-card overflow-hidden">
          {/* Video player */}
          {videoUrl && (
            <video
              src={videoUrl}
              controls
              autoPlay
              className="w-full"
            />
          )}
          
          {/* Event details */}
          <div className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <Shield className="w-5 h-5 text-purrple-400" />
                  {event.rule_name || 'Detection Event'}
                </h2>
                <p className="text-gray-400 mt-1">{event.message}</p>
              </div>
              <span className={clsx(
                'px-3 py-1 text-sm font-medium rounded-lg',
                event.state === 'triggered' && 'bg-alert-red/20 text-alert-red',
                event.state === 'recording' && 'bg-alert-orange/20 text-alert-orange',
                event.state === 'cooldown' && 'bg-catblue-500/20 text-catblue-400',
                event.state === 'idle' && 'bg-gray-500/20 text-gray-400',
              )}>
                {event.state}
              </span>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div className="bg-midnight-800/50 p-3 rounded-lg">
                <div className="text-gray-500 mb-1">Camera</div>
                <div className="font-medium">{event.camera_name || 'Unknown'}</div>
              </div>
              <div className="bg-midnight-800/50 p-3 rounded-lg">
                <div className="text-gray-500 mb-1">Triggered</div>
                <div className="font-medium">
                  {format(parseISO(event.triggered_at), 'MMM d, h:mm a')}
                </div>
              </div>
              <div className="bg-midnight-800/50 p-3 rounded-lg">
                <div className="text-gray-500 mb-1">Duration</div>
                <div className="font-medium">
                  {event.duration_seconds 
                    ? formatDuration(event.duration_seconds)
                    : 'N/A'}
                </div>
              </div>
              <div className="bg-midnight-800/50 p-3 rounded-lg">
                <div className="text-gray-500 mb-1">Detection</div>
                <div className="font-medium flex items-center gap-1">
                  {event.primary_target}
                  {event.secondary_target && (
                    <span className="text-gray-500">→ {event.secondary_target}</span>
                  )}
                </div>
              </div>
            </div>
            
            {/* Detected objects */}
            {event.detected_objects?.length > 0 && (
              <div className="mt-4">
                <div className="text-gray-500 text-sm mb-2">Detected Objects</div>
                <div className="flex flex-wrap gap-2">
                  {event.detected_objects.map((obj, i) => {
                    // Handle spatial relationship objects (primary/secondary)
                    if (obj.primary && obj.secondary) {
                      return (
                        <div key={i} className="flex items-center gap-2">
                          <span className="px-2 py-1 bg-purrple-500/20 text-purrple-400 text-sm rounded">
                            {obj.primary.label} ({(obj.primary.confidence * 100).toFixed(0)}%)
                          </span>
                          <span className="text-gray-500 text-sm">{obj.relationship || '→'}</span>
                          <span className="px-2 py-1 bg-catblue-500/20 text-catblue-400 text-sm rounded">
                            {obj.secondary.label} ({(obj.secondary.confidence * 100).toFixed(0)}%)
                          </span>
                        </div>
                      )
                    }
                    // Handle simple detection objects
                    const label = obj.label || obj.class_name || 'object'
                    const confidence = obj.confidence
                    return (
                      <span 
                        key={i}
                        className="px-2 py-1 bg-purrple-500/20 text-purrple-400 text-sm rounded"
                      >
                        {label}
                        {confidence && ` (${(confidence * 100).toFixed(0)}%)`}
                      </span>
                    )
                  })}
                </div>
              </div>
            )}
            
            {/* Recording info */}
            {hasRecording && (
              <div className="mt-4 pt-4 border-t border-midnight-700">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">
                    Recording: {event.recording.filename}
                  </span>
                  <span className="text-gray-500">
                    {(event.recording.file_size_bytes / 1024 / 1024).toFixed(1)} MB
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function EmptyState({ totalCount, viewMode, stats, onSwitchView }) {
  // If we have total events but none shown, it means filters are active
  const hasFilters = totalCount > 0
  const hasRecordings = stats?.total_recordings > 0
  
  return (
    <div className="glass-card p-12 text-center">
      <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-gradient-to-br from-midnight-800 to-midnight-700 flex items-center justify-center">
        {hasFilters ? (
          <Filter className="w-10 h-10 text-gray-600" />
        ) : viewMode === 'recordings' ? (
          <Video className="w-10 h-10 text-gray-600" />
        ) : (
          <Cat className="w-10 h-10 text-gray-600" />
        )}
      </div>
      
      <h3 className="text-xl font-bold mb-2">
        {hasFilters 
          ? 'No matching events' 
          : viewMode === 'recordings' 
            ? 'No recordings yet'
            : 'No detection events yet'
        }
      </h3>
      
      <p className="text-gray-500 max-w-md mx-auto">
        {hasFilters ? (
          'Try adjusting your filters to see more results.'
        ) : viewMode === 'recordings' ? (
          'Recordings will appear here when alerts are triggered.'
        ) : (
          <>
            When your Purrimeter Defense system detects a rule violation, 
            events will appear here with video recordings and details.
            <br /><br />
            <span className="text-purrple-400">
              🐱 Your counters are being watched!
            </span>
          </>
        )}
      </p>
      
      {/* Show switch to recordings if we have recordings but no events */}
      {viewMode === 'events' && !hasFilters && hasRecordings && (
        <button
          onClick={onSwitchView}
          className="btn-primary mt-6"
        >
          <Video className="w-4 h-4 inline mr-2" />
          View {stats.total_recordings} Recording{stats.total_recordings !== 1 ? 's' : ''}
        </button>
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
            <h3 className="font-medium truncate text-sm">{recording.filename}</h3>
            <p className="text-sm text-gray-500 flex items-center gap-1">
              <Calendar className="w-3 h-3" />
              {formatDistanceToNow(parseISO(recording.started_at), { addSuffix: true })}
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

function RecordingPlayerModal({ recording, onClose }) {
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
            {format(parseISO(recording.started_at), 'PPpp')}
          </p>
        </div>
      </div>
    </div>
  )
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '0:00'
  
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  
  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`
}
