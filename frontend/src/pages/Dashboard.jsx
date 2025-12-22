import { useEffect, useState } from 'react'
import { 
  Camera, 
  Shield, 
  Video, 
  AlertTriangle, 
  Activity,
  Clock,
  TrendingUp
} from 'lucide-react'
import { useCameraStore } from '../stores/cameraStore'
import { useRuleStore } from '../stores/ruleStore'
import { useAlertStore } from '../stores/alertStore'
import VideoFeed from '../components/VideoFeed'
import clsx from 'clsx'
import { API_URL } from '../config'

export default function Dashboard() {
  const { cameras, fetchCameras } = useCameraStore()
  const { rules, fetchRules } = useRuleStore()
  const { activeAlerts, alertHistory } = useAlertStore()
  const [stats, setStats] = useState(null)
  
  useEffect(() => {
    fetchCameras()
    fetchRules()
    fetchStats()
  }, [])
  
  const fetchStats = async () => {
    try {
      const [recordingStats, alertStats] = await Promise.all([
        fetch(`${API_URL}/api/recordings/stats/summary`).then(r => r.json()),
        fetch(`${API_URL}/api/alerts/stats/summary`).then(r => r.json()),
      ])
      setStats({ recordings: recordingStats, alerts: alertStats })
    } catch (e) {
      console.error('Stats fetch error:', e)
    }
  }
  
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">
            <span className="gradient-text">Purrimeter</span> Command Center
          </h1>
          <p className="text-gray-400 mt-1">
            Your counters are under watchful protection 🐱
          </p>
        </div>
        
        <div className="flex items-center gap-4">
          <StatusIndicator 
            active={activeAlerts.length > 0}
            label={activeAlerts.length > 0 ? "ALERT ACTIVE" : "All Clear"}
          />
        </div>
      </div>
      
      {/* Stats cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard 
          icon={Camera}
          label="Active Cameras"
          value={cameras.filter(c => c.enabled).length}
          total={cameras.length}
          color="blue"
        />
        <StatCard 
          icon={Shield}
          label="Defense Rules"
          value={rules.filter(r => r.enabled).length}
          total={rules.length}
          color="orange"
        />
        <StatCard 
          icon={Video}
          label="Recordings Today"
          value={stats?.recordings?.total_recordings || 0}
          color="purple"
        />
        <StatCard 
          icon={AlertTriangle}
          label="Alerts Today"
          value={stats?.alerts?.total_alerts || 0}
          color={stats?.alerts?.total_alerts > 0 ? "red" : "green"}
        />
      </div>
      
      {/* Live feeds grid */}
      <section>
        <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-purrple-400" />
          Live Camera Feeds
        </h2>
        
        {cameras.length === 0 ? (
          <EmptyState 
            icon={Camera}
            title="No cameras configured"
            description="Add your first camera to start protecting your counters!"
            action={{
              label: "Add Camera",
              href: "/cameras"
            }}
          />
        ) : (
          <div className="video-grid">
            {cameras.filter(c => c.enabled).map(camera => (
              <VideoFeed 
                key={camera.id}
                camera={camera}
                isAlertActive={activeAlerts.some(a => a.cameraId === camera.id)}
              />
            ))}
          </div>
        )}
      </section>
      
      {/* Recent activity */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Alert history */}
        <div className="glass-card p-6">
          <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-alert-orange" />
            Recent Alerts
          </h3>
          
          {alertHistory.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <Shield className="w-12 h-12 mx-auto mb-2 opacity-30" />
              <p>No alerts yet - your counters are safe!</p>
            </div>
          ) : (
            <div className="space-y-3 max-h-80 overflow-y-auto">
              {alertHistory.slice(0, 10).map((alert, i) => (
                <AlertHistoryItem key={i} alert={alert} />
              ))}
            </div>
          )}
        </div>
        
        {/* Active rules */}
        <div className="glass-card p-6">
          <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5 text-purrple-400" />
            Active Defense Rules
          </h3>
          
          {rules.filter(r => r.enabled).length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <Shield className="w-12 h-12 mx-auto mb-2 opacity-30" />
              <p>No rules configured yet</p>
            </div>
          ) : (
            <div className="space-y-3 max-h-80 overflow-y-auto">
              {rules.filter(r => r.enabled).map(rule => (
                <RuleItem key={rule.id} rule={rule} />
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

function StatusIndicator({ active, label }) {
  return (
    <div className={clsx(
      "flex items-center gap-2 px-4 py-2 rounded-full font-semibold",
      active 
        ? "bg-alert-red/20 text-alert-red border border-alert-red/50 animate-pulse"
        : "bg-alert-green/20 text-alert-green border border-alert-green/50"
    )}>
      <div className={clsx(
        "w-3 h-3 rounded-full",
        active ? "bg-alert-red animate-ping" : "bg-alert-green"
      )} />
      {label}
    </div>
  )
}

function StatCard({ icon: Icon, label, value, total, color }) {
  const colorClasses = {
    blue: 'text-catblue-400 bg-catblue-500/10 border-catblue-500/30',
    orange: 'text-purrple-400 bg-purrple-500/10 border-purrple-500/30',
    purple: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
    green: 'text-alert-green bg-alert-green/10 border-alert-green/30',
    red: 'text-alert-red bg-alert-red/10 border-alert-red/30',
  }
  
  return (
    <div className={clsx(
      "glass-card p-6 border",
      colorClasses[color]
    )}>
      <div className="flex items-center justify-between mb-4">
        <Icon className="w-8 h-8" />
        {total !== undefined && (
          <span className="text-sm opacity-60">/{total}</span>
        )}
      </div>
      <div className="text-3xl font-bold mb-1">{value}</div>
      <div className="text-sm opacity-60">{label}</div>
    </div>
  )
}

function AlertHistoryItem({ alert }) {
  const timeAgo = getTimeAgo(new Date(alert.triggeredAt))
  
  return (
    <div className="flex items-center gap-3 p-3 bg-midnight-800/50 rounded-lg">
      <div className="w-10 h-10 rounded-full bg-alert-red/20 flex items-center justify-center">
        <AlertTriangle className="w-5 h-5 text-alert-red" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate">{alert.message}</p>
        <p className="text-sm text-gray-500">{alert.rule_name}</p>
      </div>
      <div className="text-sm text-gray-500 flex items-center gap-1">
        <Clock className="w-3 h-3" />
        {timeAgo}
      </div>
    </div>
  )
}

function RuleItem({ rule }) {
  return (
    <div className="flex items-center gap-3 p-3 bg-midnight-800/50 rounded-lg">
      <div className="w-10 h-10 rounded-full bg-purrple-500/20 flex items-center justify-center">
        <Shield className="w-5 h-5 text-purrple-400" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate">{rule.name}</p>
        <p className="text-sm text-gray-500">
          {rule.primary_target}
          {rule.secondary_target && ` → ${rule.secondary_target}`}
        </p>
      </div>
      <div className="text-xs px-2 py-1 bg-purrple-500/20 text-purrple-400 rounded">
        {rule.condition_type.replace('_', ' ')}
      </div>
    </div>
  )
}

function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="glass-card p-12 text-center">
      <Icon className="w-16 h-16 mx-auto mb-4 text-gray-600" />
      <h3 className="text-xl font-bold mb-2">{title}</h3>
      <p className="text-gray-500 mb-6">{description}</p>
      {action && (
        <a href={action.href} className="btn-primary inline-block">
          {action.label}
        </a>
      )}
    </div>
  )
}

function getTimeAgo(date) {
  const seconds = Math.floor((new Date() - date) / 1000)
  
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

