import { Outlet, NavLink } from 'react-router-dom'
import { 
  Camera, 
  Shield, 
  Video, 
  Settings, 
  Bell, 
  Wifi, 
  WifiOff,
  Home
} from 'lucide-react'
import { useAlertStore } from '../stores/alertStore'
import AlertBanner from './AlertBanner'
import clsx from 'clsx'

const navItems = [
  { path: '/', label: 'Dashboard', icon: Home },
  { path: '/cameras', label: 'Cameras', icon: Camera },
  { path: '/rules', label: 'Rules', icon: Shield },
  { path: '/recordings', label: 'Recordings', icon: Video },
  { path: '/settings', label: 'Settings', icon: Settings },
]

export default function Layout() {
  const { connected, activeAlerts } = useAlertStore()
  
  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-midnight-900/90 backdrop-blur-lg border-r border-midnight-700 flex flex-col h-screen sticky top-0">
        {/* Logo - fixed height */}
        <div className="flex-shrink-0 p-6 border-b border-midnight-700">
          <div className="flex items-center gap-3">
            <div className="relative">
              <img 
                src="/cat-icon.svg" 
                alt="Purrimeter" 
                className="w-12 h-12 animate-bounce-subtle"
              />
              {activeAlerts.length > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-alert-red rounded-full animate-pulse" />
              )}
            </div>
            <div>
              <h1 className="text-xl font-bold gradient-text">Purrimeter</h1>
              <p className="text-xs text-gray-500">Defense System</p>
            </div>
          </div>
        </div>
        
        {/* Navigation - scrollable if needed */}
        <nav className="flex-1 overflow-y-auto p-4 space-y-2">
          {navItems.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) => clsx(
                'flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200',
                isActive 
                  ? 'bg-purrple-500/20 text-purrple-400 border border-purrple-500/30'
                  : 'text-gray-400 hover:bg-midnight-800 hover:text-gray-200'
              )}
            >
              <Icon className="w-5 h-5" />
              <span className="font-medium">{label}</span>
            </NavLink>
          ))}
        </nav>
        
        {/* Status - fixed at bottom */}
        <div className="flex-shrink-0 p-4 border-t border-midnight-700">
          <div className="glass-card p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-gray-400">Status</span>
              <div className="flex items-center gap-2">
                {connected ? (
                  <>
                    <Wifi className="w-4 h-4 text-alert-green" />
                    <span className="text-xs text-alert-green">Connected</span>
                  </>
                ) : (
                  <>
                    <WifiOff className="w-4 h-4 text-alert-red" />
                    <span className="text-xs text-alert-red">Disconnected</span>
                  </>
                )}
              </div>
            </div>
            
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Active Alerts</span>
              <div className="flex items-center gap-2">
                <Bell className={clsx(
                  "w-4 h-4",
                  activeAlerts.length > 0 ? "text-alert-red animate-wiggle" : "text-gray-500"
                )} />
                <span className={clsx(
                  "text-sm font-bold",
                  activeAlerts.length > 0 ? "text-alert-red" : "text-gray-500"
                )}>
                  {activeAlerts.length}
                </span>
              </div>
            </div>
          </div>
        </div>
      </aside>
      
      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Alert banner */}
        <AlertBanner />
        
        {/* Page content */}
        <div className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

