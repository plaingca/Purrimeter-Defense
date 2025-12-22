import { useState, useEffect } from 'react'
import { 
  Settings as SettingsIcon, 
  Bell, 
  Zap, 
  TestTube,
  CheckCircle,
  XCircle,
  RefreshCw,
  MessageSquare,
  Plug,
  Volume2,
  Webhook,
  Camera,
  Save,
  Eye,
  EyeOff
} from 'lucide-react'
import clsx from 'clsx'
import { API_URL } from '../config'

export default function Settings() {
  const [testResults, setTestResults] = useState({})
  const [testing, setTesting] = useState({})
  
  // Tapo camera config state
  const [tapoConfig, setTapoConfig] = useState({
    camera_ip: '',
    camera_user: '',
    camera_password: '',
  })
  const [tapoStatus, setTapoStatus] = useState(null)
  const [showPassword, setShowPassword] = useState(false)
  const [tapoTestResult, setTapoTestResult] = useState(null)
  const [tapoTesting, setTapoTesting] = useState(false)
  const [tapoSpeakerTesting, setTapoSpeakerTesting] = useState(false)
  const [tapoSpeakerResult, setTapoSpeakerResult] = useState(null)
  
  // Fetch Tapo status on mount
  useEffect(() => {
    fetchTapoStatus()
  }, [])
  
  const fetchTapoStatus = async () => {
    try {
      const response = await fetch(`${API_URL}/api/actions/tapo/status`)
      const data = await response.json()
      setTapoStatus(data)
      if (data.camera_ip) {
        setTapoConfig(prev => ({
          ...prev,
          camera_ip: data.camera_ip,
          camera_user: data.camera_user || '',
        }))
      }
    } catch (error) {
      console.error('Failed to fetch Tapo status:', error)
    }
  }
  
  const testTapoConnection = async () => {
    if (!tapoConfig.camera_ip || !tapoConfig.camera_user || !tapoConfig.camera_password) {
      setTapoTestResult({ success: false, message: 'Please fill in all fields' })
      return
    }
    
    setTapoTesting(true)
    setTapoTestResult(null)
    
    try {
      const response = await fetch(`${API_URL}/api/actions/tapo/test-connection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(tapoConfig),
      })
      
      const result = await response.json()
      setTapoTestResult(result)
    } catch (error) {
      setTapoTestResult({ success: false, message: 'Connection failed', error: error.message })
    } finally {
      setTapoTesting(false)
    }
  }
  
  const testTapoSpeaker = async () => {
    if (!tapoConfig.camera_ip || !tapoConfig.camera_user || !tapoConfig.camera_password) {
      setTapoSpeakerResult({ success: false, message: 'Please configure camera first' })
      return
    }
    
    setTapoSpeakerTesting(true)
    setTapoSpeakerResult(null)
    
    try {
      const response = await fetch(`${API_URL}/api/actions/tapo/test-speaker`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...tapoConfig,
          sound_type: 'alarm',
          duration: 2,
        }),
      })
      
      const result = await response.json()
      setTapoSpeakerResult(result)
    } catch (error) {
      setTapoSpeakerResult({ success: false, message: 'Speaker test failed', error: error.message })
    } finally {
      setTapoSpeakerTesting(false)
    }
  }
  
  const testAction = async (actionType, params = {}) => {
    setTesting(prev => ({ ...prev, [actionType]: true }))
    
    try {
      const response = await fetch(`${API_URL}/api/actions/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action_type: actionType, params }),
      })
      
      const result = await response.json()
      setTestResults(prev => ({ ...prev, [actionType]: result }))
    } catch (error) {
      setTestResults(prev => ({
        ...prev,
        [actionType]: { success: false, error: error.message },
      }))
    } finally {
      setTesting(prev => ({ ...prev, [actionType]: false }))
    }
  }
  
  return (
    <div className="space-y-8 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <SettingsIcon className="w-8 h-8 text-purrple-400" />
          Settings
        </h1>
        <p className="text-gray-400 mt-1">
          Configure your Purrimeter Defense system
        </p>
      </div>
      
      {/* Action integrations */}
      <section className="glass-card p-6">
        <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
          <Zap className="w-5 h-5 text-purrple-400" />
          Action Integrations
        </h2>
        
        <div className="space-y-6">
          {/* Discord */}
          <IntegrationCard
            icon={MessageSquare}
            title="Discord Webhook"
            description="Send alert notifications and recordings to Discord"
            onTest={() => testAction('discord_webhook', { message: '🐱 Test message from Purrimeter Defense!' })}
            testing={testing['discord_webhook']}
            result={testResults['discord_webhook']}
          >
            <div className="mt-4">
              <p className="text-sm text-gray-500 mb-2">
                Configure your webhook URL in the environment variables:
              </p>
              <code className="text-xs bg-midnight-800 px-3 py-2 rounded block font-mono">
                DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
              </code>
            </div>
          </IntegrationCard>
          
          {/* Kasa Smart Plug */}
          <IntegrationCard
            icon={Plug}
            title="Kasa Smart Plug"
            description="Control TP-Link Kasa smart plugs to trigger deterrents"
            onTest={() => testAction('kasa_smart_plug', { action: 'pulse' })}
            testing={testing['kasa_smart_plug']}
            result={testResults['kasa_smart_plug']}
          >
            <div className="mt-4">
              <p className="text-sm text-gray-500 mb-2">
                Configure your Kasa device IP in environment variables:
              </p>
              <code className="text-xs bg-midnight-800 px-3 py-2 rounded block font-mono">
                KASA_DEVICE_IP=192.168.1.100
              </code>
            </div>
          </IntegrationCard>
          
          {/* HTTP Webhook */}
          <IntegrationCard
            icon={Webhook}
            title="HTTP Webhook"
            description="Send custom HTTP requests to external services"
            onTest={() => testAction('http_request', { 
              url: 'https://httpbin.org/post',
              method: 'POST',
              body: { test: true },
            })}
            testing={testing['http_request']}
            result={testResults['http_request']}
          >
            <div className="mt-4 text-sm text-gray-500">
              <p>Configure HTTP webhooks in rule actions to integrate with:</p>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>Home Assistant</li>
                <li>IFTTT</li>
                <li>Zapier</li>
                <li>Custom APIs</li>
              </ul>
            </div>
          </IntegrationCard>
          
          {/* Sound */}
          <IntegrationCard
            icon={Volume2}
            title="Sound Alerts"
            description="Play sound files to scare cats away"
            onTest={() => testAction('play_sound', { sound_file: '/app/sounds/alert.wav' })}
            testing={testing['play_sound']}
            result={testResults['play_sound']}
          >
            <div className="mt-4 text-sm text-gray-500">
              <p>Place .wav sound files in the /app/sounds directory.</p>
              <p className="mt-2">Recommended sounds:</p>
              <ul className="list-disc list-inside mt-1 space-y-1">
                <li>Short hissing sounds</li>
                <li>Compressed air spray sounds</li>
                <li>Ultrasonic deterrent tones</li>
              </ul>
            </div>
          </IntegrationCard>
          
          {/* Tapo Camera Speaker */}
          <div className="p-4 bg-midnight-800/50 rounded-xl">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg bg-purrple-500/20 flex items-center justify-center flex-shrink-0">
                <Camera className="w-5 h-5 text-purrple-400" />
              </div>
              <div className="flex-1">
                <h3 className="font-bold">Tapo Camera Speaker</h3>
                <p className="text-sm text-gray-500">
                  Play sounds through your Tapo camera's built-in speaker (C210, C220, etc.)
                </p>
                
                {/* Status badge */}
                {tapoStatus && (
                  <div className={clsx(
                    "inline-flex items-center gap-1.5 mt-2 px-2 py-1 rounded-full text-xs",
                    tapoStatus.configured 
                      ? "bg-alert-green/20 text-alert-green"
                      : "bg-gray-700 text-gray-400"
                  )}>
                    {tapoStatus.configured ? (
                      <>
                        <CheckCircle className="w-3 h-3" />
                        Configured
                      </>
                    ) : (
                      <>
                        <XCircle className="w-3 h-3" />
                        Not configured
                      </>
                    )}
                  </div>
                )}
                
                {/* Configuration form */}
                <div className="mt-4 space-y-3">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Camera IP Address</label>
                    <input
                      type="text"
                      value={tapoConfig.camera_ip}
                      onChange={e => setTapoConfig(prev => ({ ...prev, camera_ip: e.target.value }))}
                      placeholder="192.168.1.101"
                      className="input-field text-sm"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Camera Account Username</label>
                    <input
                      type="text"
                      value={tapoConfig.camera_user}
                      onChange={e => setTapoConfig(prev => ({ ...prev, camera_user: e.target.value }))}
                      placeholder="admin"
                      className="input-field text-sm"
                    />
                    <p className="text-xs text-gray-600 mt-1">
                      Set in Tapo app: Settings → Advanced Settings → Camera Account
                    </p>
                  </div>
                  
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Camera Account Password</label>
                    <div className="relative">
                      <input
                        type={showPassword ? "text" : "password"}
                        value={tapoConfig.camera_password}
                        onChange={e => setTapoConfig(prev => ({ ...prev, camera_password: e.target.value }))}
                        placeholder="••••••••"
                        className="input-field text-sm pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-300"
                      >
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                  
                  {/* Test buttons */}
                  <div className="flex gap-2 pt-2">
                    <button
                      type="button"
                      onClick={testTapoConnection}
                      disabled={tapoTesting}
                      className="btn-secondary py-2 px-4 flex items-center gap-2 text-sm"
                    >
                      {tapoTesting ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <TestTube className="w-4 h-4" />
                      )}
                      Test Connection
                    </button>
                    
                    <button
                      type="button"
                      onClick={testTapoSpeaker}
                      disabled={tapoSpeakerTesting || !tapoTestResult?.success}
                      className={clsx(
                        "py-2 px-4 flex items-center gap-2 text-sm rounded-lg transition-colors",
                        tapoTestResult?.success
                          ? "bg-purrple-500 hover:bg-purrple-600 text-white"
                          : "bg-gray-700 text-gray-500 cursor-not-allowed"
                      )}
                    >
                      {tapoSpeakerTesting ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Volume2 className="w-4 h-4" />
                      )}
                      Test Speaker
                    </button>
                  </div>
                  
                  {/* Connection test result */}
                  {tapoTestResult && (
                    <div className={clsx(
                      "p-3 rounded-lg flex items-center gap-2 text-sm",
                      tapoTestResult.success 
                        ? "bg-alert-green/20 text-alert-green"
                        : "bg-alert-red/20 text-alert-red"
                    )}>
                      {tapoTestResult.success ? (
                        <CheckCircle className="w-4 h-4 flex-shrink-0" />
                      ) : (
                        <XCircle className="w-4 h-4 flex-shrink-0" />
                      )}
                      <span>{tapoTestResult.message}</span>
                      {tapoTestResult.error && (
                        <span className="text-xs opacity-70">({tapoTestResult.error})</span>
                      )}
                    </div>
                  )}
                  
                  {/* Speaker test result */}
                  {tapoSpeakerResult && (
                    <div className={clsx(
                      "p-3 rounded-lg flex items-center gap-2 text-sm",
                      tapoSpeakerResult.success 
                        ? "bg-alert-green/20 text-alert-green"
                        : "bg-alert-red/20 text-alert-red"
                    )}>
                      {tapoSpeakerResult.success ? (
                        <CheckCircle className="w-4 h-4 flex-shrink-0" />
                      ) : (
                        <XCircle className="w-4 h-4 flex-shrink-0" />
                      )}
                      <span>{tapoSpeakerResult.message}</span>
                    </div>
                  )}
                </div>
                
                <div className="mt-4 p-3 bg-midnight-900/50 rounded-lg">
                  <p className="text-xs text-gray-500">
                    <strong>Note:</strong> Camera credentials entered here are used only for testing. 
                    To persist settings, add them to your environment variables:
                  </p>
                  <code className="text-xs bg-midnight-800 px-2 py-1 rounded block font-mono mt-2 text-gray-400">
                    TAPO_CAMERA_IP={tapoConfig.camera_ip || '192.168.1.101'}<br/>
                    TAPO_CAMERA_USER={tapoConfig.camera_user || 'admin'}<br/>
                    TAPO_CAMERA_PASSWORD=your_password
                  </code>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      
      {/* Detection settings */}
      <section className="glass-card p-6">
        <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
          <Bell className="w-5 h-5 text-purrple-400" />
          Detection Settings
        </h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <SettingItem
            label="Detection Sample Rate"
            description="How many times per second to run detection"
            value="2 samples/sec"
            envVar="DETECTION_SAMPLE_RATE"
          />
          
          <SettingItem
            label="Confidence Threshold"
            description="Minimum confidence to count as detection"
            value="50%"
            envVar="DETECTION_CONFIDENCE_THRESHOLD"
          />
          
          <SettingItem
            label="Pre-roll Duration"
            description="Seconds of video before alert to include in recording"
            value="5 seconds"
            envVar="RECORDING_PRE_ROLL_SECONDS"
          />
          
          <SettingItem
            label="Post-roll Duration"
            description="Seconds of video after alert ends"
            value="3 seconds"
            envVar="RECORDING_POST_ROLL_SECONDS"
          />
        </div>
      </section>
      
      {/* About */}
      <section className="glass-card p-6">
        <div className="flex items-center gap-4">
          <img src="/cat-icon.svg" alt="Purrimeter" className="w-16 h-16" />
          <div>
            <h2 className="text-xl font-bold">Purrimeter Defense</h2>
            <p className="text-gray-500">
              Vision-based intrusion detection for enforcing strict counter boundaries
            </p>
            <p className="text-sm text-gray-600 mt-1">
              Powered by SAM3 (Segment Anything Model 3) from Meta AI
            </p>
          </div>
        </div>
        
        <div className="mt-6 p-4 bg-midnight-800/50 rounded-xl">
          <h3 className="font-medium mb-2">🐱 How it works</h3>
          <ol className="list-decimal list-inside text-sm text-gray-400 space-y-1">
            <li>Connect your RTSP cameras</li>
            <li>Create detection rules (e.g., "cat over counter")</li>
            <li>SAM3 analyzes frames in real-time</li>
            <li>Alerts trigger recordings and actions</li>
            <li>Review recordings and fine-tune your defenses</li>
          </ol>
        </div>
      </section>
    </div>
  )
}

function IntegrationCard({ icon: Icon, title, description, onTest, testing, result, children }) {
  return (
    <div className="p-4 bg-midnight-800/50 rounded-xl">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 rounded-lg bg-purrple-500/20 flex items-center justify-center flex-shrink-0">
            <Icon className="w-5 h-5 text-purrple-400" />
          </div>
          <div>
            <h3 className="font-bold">{title}</h3>
            <p className="text-sm text-gray-500">{description}</p>
          </div>
        </div>
        
        <button
          onClick={onTest}
          disabled={testing}
          className="btn-secondary py-2 px-4 flex items-center gap-2 text-sm"
        >
          {testing ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <TestTube className="w-4 h-4" />
          )}
          Test
        </button>
      </div>
      
      {/* Test result */}
      {result && (
        <div className={clsx(
          "mt-4 p-3 rounded-lg flex items-center gap-2 text-sm",
          result.success 
            ? "bg-alert-green/20 text-alert-green"
            : "bg-alert-red/20 text-alert-red"
        )}>
          {result.success ? (
            <CheckCircle className="w-4 h-4" />
          ) : (
            <XCircle className="w-4 h-4" />
          )}
          <span>{result.message || (result.success ? 'Success!' : 'Failed')}</span>
          {result.error && <span className="text-xs opacity-70">({result.error})</span>}
        </div>
      )}
      
      {children}
    </div>
  )
}

function SettingItem({ label, description, value, envVar }) {
  return (
    <div className="p-4 bg-midnight-800/50 rounded-xl">
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-medium">{label}</h4>
        <span className="text-purrple-400 font-mono text-sm">{value}</span>
      </div>
      <p className="text-sm text-gray-500 mb-2">{description}</p>
      <code className="text-xs bg-midnight-900 px-2 py-1 rounded font-mono text-gray-500">
        {envVar}
      </code>
    </div>
  )
}

