import { useAlertStore } from '../stores/alertStore'
import { AlertTriangle, X } from 'lucide-react'
import clsx from 'clsx'

export default function AlertBanner() {
  const { activeAlerts } = useAlertStore()
  
  if (activeAlerts.length === 0) return null
  
  const latestAlert = activeAlerts[activeAlerts.length - 1]
  
  return (
    <div className="alert-banner bg-gradient-to-r from-alert-red/90 to-alert-orange/90 backdrop-blur-sm border-b border-alert-red">
      <div className="flex items-center justify-between px-6 py-3">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 animate-pulse">
            <AlertTriangle className="w-6 h-6" />
            <span className="text-lg font-bold">🚨 ALERT!</span>
          </div>
          
          <div className="flex items-center gap-3">
            <span className="font-medium">{latestAlert.message}</span>
            <span className="text-sm opacity-80">
              ({Math.round(latestAlert.confidence * 100)}% confidence)
            </span>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {activeAlerts.length > 1 && (
            <span className="px-3 py-1 bg-white/20 rounded-full text-sm">
              +{activeAlerts.length - 1} more
            </span>
          )}
          
          <CatEmoji />
        </div>
      </div>
    </div>
  )
}

function CatEmoji() {
  return (
    <span className="text-2xl animate-cat-walk inline-block">
      🐱
    </span>
  )
}

