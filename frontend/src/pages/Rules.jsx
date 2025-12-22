import { useEffect, useState, useMemo } from 'react'
import { 
  Shield, 
  Plus, 
  Edit2, 
  Trash2, 
  Zap,
  X,
  Check,
  ChevronDown,
  Settings,
  Play,
  Eye,
  Bell,
  Volume2,
  Webhook,
  Power,
  Camera
} from 'lucide-react'
import { useRuleStore } from '../stores/ruleStore'
import { useCameraStore } from '../stores/cameraStore'
import DetectionPreview from '../components/DetectionPreview'
import clsx from 'clsx'

const CONDITION_TYPES = [
  { value: 'object_detected', label: 'Object Detected', description: 'Trigger when object is visible' },
  { value: 'object_in_zone', label: 'Object in Zone', description: 'Trigger when object enters a defined area' },
  { value: 'object_over_object', label: 'Object Over Object', description: 'Trigger when one object is above another (e.g., cat over counter)' },
  { value: 'object_count', label: 'Object Count', description: 'Trigger when object count exceeds threshold' },
]

const ACTION_TYPES = [
  { 
    type: 'discord_webhook', 
    label: 'Discord Notification', 
    icon: Bell,
    description: 'Send a message to Discord',
    params: [
      { key: 'message', label: 'Message', type: 'text', default: '🚨 Alert triggered!' },
    ]
  },
  { 
    type: 'kasa_smart_plug', 
    label: 'Smart Plug', 
    icon: Power,
    description: 'Control a Kasa smart plug',
    params: [
      { key: 'action', label: 'Action', type: 'select', options: ['toggle', 'on', 'off', 'pulse'], default: 'toggle' },
      { key: 'duration', label: 'Duration (sec)', type: 'number', default: 3 },
      { key: 'device_ip', label: 'Device IP (optional)', type: 'text', default: '' },
    ]
  },
  { 
    type: 'http_request', 
    label: 'HTTP Request', 
    icon: Webhook,
    description: 'Make an HTTP request',
    params: [
      { key: 'url', label: 'URL', type: 'text', default: '' },
      { key: 'method', label: 'Method', type: 'select', options: ['POST', 'GET', 'PUT'], default: 'POST' },
    ]
  },
  { 
    type: 'play_sound', 
    label: 'Play Sound', 
    icon: Volume2,
    description: 'Play a sound file locally',
    params: [
      { key: 'sound_file', label: 'Sound File Path', type: 'text', default: '/app/sounds/alert.wav' },
    ]
  },
  { 
    type: 'tapo_speaker', 
    label: 'Tapo Camera Speaker', 
    icon: Camera,
    description: 'Play alarm through Tapo camera speaker',
    params: [
      { key: 'sound_type', label: 'Sound Type', type: 'select', options: ['alarm', 'siren'], default: 'alarm' },
      { key: 'duration', label: 'Duration (sec)', type: 'number', default: 3 },
      { key: 'camera_ip', label: 'Camera IP (optional)', type: 'text', default: '' },
    ]
  },
]

export default function Rules() {
  const { rules, presets, loading, fetchRules, fetchPresets, addRule, updateRule, deleteRule, applyPreset } = useRuleStore()
  const { cameras, fetchCameras } = useCameraStore()
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingRule, setEditingRule] = useState(null)
  const [showPresetModal, setShowPresetModal] = useState(false)
  
  useEffect(() => {
    fetchRules()
    fetchPresets()
    fetchCameras()
  }, [])
  
  const handleDelete = async (rule) => {
    if (confirm(`Are you sure you want to delete "${rule.name}"?`)) {
      await deleteRule(rule.id)
    }
  }
  
  const handleApplyPreset = async (presetId, cameraId) => {
    await applyPreset(presetId, cameraId)
    setShowPresetModal(false)
  }
  
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Shield className="w-8 h-8 text-purrple-400" />
            Detection Rules
          </h1>
          <p className="text-gray-400 mt-1">
            Define what triggers alerts and what actions to take
          </p>
        </div>
        
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setShowPresetModal(true)}
            className="btn-secondary flex items-center gap-2"
          >
            <Zap className="w-5 h-5" />
            Quick Presets
          </button>
          <button 
            onClick={() => setShowAddModal(true)}
            className="btn-primary flex items-center gap-2"
          >
            <Plus className="w-5 h-5" />
            Create Rule
          </button>
        </div>
      </div>
      
      {/* Rules list */}
      {rules.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <Shield className="w-16 h-16 mx-auto mb-4 text-gray-600" />
          <h3 className="text-xl font-bold mb-2">No rules configured</h3>
          <p className="text-gray-500 mb-6">
            Create detection rules to start protecting your counters from mischievous kitties!
          </p>
          <div className="flex gap-4 justify-center">
            <button 
              onClick={() => setShowPresetModal(true)}
              className="btn-secondary"
            >
              Use a Preset
            </button>
            <button 
              onClick={() => setShowAddModal(true)}
              className="btn-primary"
            >
              Create Custom Rule
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {rules.map(rule => (
            <RuleCard 
              key={rule.id}
              rule={rule}
              cameras={cameras}
              onEdit={() => setEditingRule(rule)}
              onDelete={() => handleDelete(rule)}
              onToggle={async () => {
                await updateRule(rule.id, { enabled: !rule.enabled })
              }}
            />
          ))}
        </div>
      )}
      
      {/* Add/Edit Modal */}
      {(showAddModal || editingRule) && (
        <RuleModal
          rule={editingRule}
          cameras={cameras}
          onClose={() => {
            setShowAddModal(false)
            setEditingRule(null)
          }}
          onSave={async (data) => {
            if (editingRule) {
              await updateRule(editingRule.id, data)
            } else {
              await addRule(data)
            }
            setShowAddModal(false)
            setEditingRule(null)
          }}
        />
      )}
      
      {/* Preset Modal */}
      {showPresetModal && (
        <PresetModal
          presets={presets}
          cameras={cameras}
          onClose={() => setShowPresetModal(false)}
          onApply={handleApplyPreset}
        />
      )}
    </div>
  )
}

function RuleCard({ rule, cameras, onEdit, onDelete, onToggle }) {
  const camera = cameras.find(c => c.id === rule.camera_id)
  const [expanded, setExpanded] = useState(false)
  
  const hasStartActions = rule.on_alert_start_actions?.length > 0
  const hasEndActions = rule.on_alert_end_actions?.length > 0
  
  return (
    <div className={clsx(
      "glass-card overflow-hidden transition-all",
      !rule.enabled && "opacity-60"
    )}>
      {/* Main row */}
      <div 
        className="p-4 flex items-center gap-4 cursor-pointer hover:bg-midnight-800/50"
        onClick={() => setExpanded(!expanded)}
      >
        <div className={clsx(
          "w-12 h-12 rounded-xl flex items-center justify-center",
          rule.enabled ? "bg-purrple-500/20" : "bg-gray-700/50"
        )}>
          <Shield className={clsx(
            "w-6 h-6",
            rule.enabled ? "text-purrple-400" : "text-gray-500"
          )} />
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <h3 className="font-bold text-lg">{rule.name}</h3>
            <span className={clsx(
              "px-2 py-0.5 text-xs rounded-full font-medium",
              rule.enabled 
                ? "bg-alert-green/20 text-alert-green"
                : "bg-gray-700 text-gray-400"
            )}>
              {rule.enabled ? 'Active' : 'Disabled'}
            </span>
            {(hasStartActions || hasEndActions) && (
              <span className="px-2 py-0.5 text-xs rounded-full bg-purrple-500/20 text-purrple-400">
                {(rule.on_alert_start_actions?.length || 0) + (rule.on_alert_end_actions?.length || 0)} actions
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500">
            {camera?.name || 'Unknown camera'} • 
            <span className="text-purrple-400"> {rule.primary_target}</span>
            {rule.secondary_target && (
              <span className="text-gray-400"> → {rule.secondary_target}</span>
            )}
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          <ConditionBadge type={rule.condition_type} />
          <ChevronDown className={clsx(
            "w-5 h-5 text-gray-500 transition-transform",
            expanded && "rotate-180"
          )} />
        </div>
      </div>
      
      {/* Expanded details */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-midnight-700">
          <div className="pt-4 grid grid-cols-2 gap-6">
            {/* Rule settings */}
            <div>
              <h4 className="text-sm font-medium text-gray-400 mb-3">Rule Settings</h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Condition</span>
                  <span>{rule.condition_type.replace(/_/g, ' ')}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Cooldown</span>
                  <span>{rule.cooldown_seconds}s</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Alert Message</span>
                  <span className="truncate max-w-40">{rule.alert_message}</span>
                </div>
              </div>
            </div>
            
            {/* Actions */}
            <div>
              <h4 className="text-sm font-medium text-gray-400 mb-3">Actions</h4>
              <div className="space-y-2">
                <ActionList label="On Alert Start" actions={rule.on_alert_start_actions} />
                <ActionList label="On Alert End" actions={rule.on_alert_end_actions} />
              </div>
            </div>
          </div>
          
          {/* Action buttons */}
          <div className="flex items-center gap-2 mt-4 pt-4 border-t border-midnight-700">
            <button
              onClick={onToggle}
              className={clsx(
                "px-4 py-2 rounded-lg flex items-center gap-2 transition-colors",
                rule.enabled 
                  ? "bg-gray-700/50 hover:bg-gray-600/50"
                  : "bg-alert-green/20 hover:bg-alert-green/30 text-alert-green"
              )}
            >
              <Play className="w-4 h-4" />
              {rule.enabled ? 'Disable' : 'Enable'}
            </button>
            <button
              onClick={onEdit}
              className="btn-secondary py-2 flex items-center gap-2"
            >
              <Edit2 className="w-4 h-4" />
              Edit
            </button>
            <button
              onClick={onDelete}
              className="btn-danger py-2 flex items-center gap-2"
            >
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function ConditionBadge({ type }) {
  const config = CONDITION_TYPES.find(c => c.value === type)
  return (
    <span className="px-3 py-1 bg-midnight-800 text-gray-300 text-xs rounded-full">
      {config?.label || type}
    </span>
  )
}

function ActionList({ label, actions }) {
  if (!actions || actions.length === 0) {
    return (
      <div className="text-sm text-gray-500">
        <span className="text-gray-600">{label}:</span> None configured
      </div>
    )
  }
  
  return (
    <div className="text-sm">
      <span className="text-gray-500">{label}:</span>
      <div className="flex flex-wrap gap-1 mt-1">
        {actions.map((action, i) => (
          <span key={i} className="px-2 py-0.5 bg-purrple-500/20 text-purrple-400 text-xs rounded">
            {ACTION_TYPES.find(a => a.type === action.type)?.label || action.type}
          </span>
        ))}
      </div>
    </div>
  )
}

function RuleModal({ rule, cameras, onClose, onSave }) {
  const [formData, setFormData] = useState({
    camera_id: rule?.camera_id || cameras[0]?.id || '',
    name: rule?.name || '',
    description: rule?.description || '',
    primary_target: rule?.primary_target || 'cat',
    secondary_target: rule?.secondary_target || '',
    condition_type: rule?.condition_type || 'object_detected',
    condition_params: rule?.condition_params || {},
    alert_message: rule?.alert_message || '🚨 Alert triggered!',
    cooldown_seconds: rule?.cooldown_seconds || 30,
    on_alert_start_actions: rule?.on_alert_start_actions || [],
    on_alert_end_actions: rule?.on_alert_end_actions || [],
    enabled: rule?.enabled ?? true,
  })
  const [saving, setSaving] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [activeTab, setActiveTab] = useState('detection')  // 'detection' | 'actions'
  
  // Get current camera
  const selectedCamera = useMemo(() => 
    cameras.find(c => c.id === formData.camera_id),
    [cameras, formData.camera_id]
  )
  
  // Build prompts for detection preview
  const detectionPrompts = useMemo(() => {
    const prompts = []
    if (formData.primary_target) prompts.push(formData.primary_target)
    if (formData.secondary_target) prompts.push(formData.secondary_target)
    return prompts
  }, [formData.primary_target, formData.secondary_target])
  
  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await onSave(formData)
    } finally {
      setSaving(false)
    }
  }
  
  const needsSecondaryTarget = ['object_over_object', 'object_in_zone'].includes(formData.condition_type)
  
  const addAction = (when, actionType) => {
    const actionDef = ACTION_TYPES.find(a => a.type === actionType)
    const params = {}
    actionDef?.params?.forEach(p => {
      params[p.key] = p.default
    })
    
    const newAction = { type: actionType, params }
    
    if (when === 'start') {
      setFormData({
        ...formData,
        on_alert_start_actions: [...formData.on_alert_start_actions, newAction]
      })
    } else {
      setFormData({
        ...formData,
        on_alert_end_actions: [...formData.on_alert_end_actions, newAction]
      })
    }
  }
  
  const removeAction = (when, index) => {
    if (when === 'start') {
      setFormData({
        ...formData,
        on_alert_start_actions: formData.on_alert_start_actions.filter((_, i) => i !== index)
      })
    } else {
      setFormData({
        ...formData,
        on_alert_end_actions: formData.on_alert_end_actions.filter((_, i) => i !== index)
      })
    }
  }
  
  const updateActionParam = (when, index, key, value) => {
    const actions = when === 'start' ? [...formData.on_alert_start_actions] : [...formData.on_alert_end_actions]
    actions[index] = {
      ...actions[index],
      params: { ...actions[index].params, [key]: value }
    }
    
    if (when === 'start') {
      setFormData({ ...formData, on_alert_start_actions: actions })
    } else {
      setFormData({ ...formData, on_alert_end_actions: actions })
    }
  }
  
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="glass-card w-full max-w-3xl p-6 my-8 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold">
            {rule ? 'Edit Rule' : 'Create Detection Rule'}
          </h2>
          <button 
            onClick={onClose}
            className="p-2 hover:bg-midnight-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        
        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          <button
            type="button"
            onClick={() => setActiveTab('detection')}
            className={clsx(
              "px-4 py-2 rounded-lg font-medium transition-colors",
              activeTab === 'detection'
                ? "bg-purrple-500 text-white"
                : "bg-midnight-800 text-gray-400 hover:text-white"
            )}
          >
            Detection Setup
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('actions')}
            className={clsx(
              "px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2",
              activeTab === 'actions'
                ? "bg-purrple-500 text-white"
                : "bg-midnight-800 text-gray-400 hover:text-white"
            )}
          >
            Alert Actions
            {(formData.on_alert_start_actions.length + formData.on_alert_end_actions.length) > 0 && (
              <span className="px-2 py-0.5 bg-white/20 rounded-full text-xs">
                {formData.on_alert_start_actions.length + formData.on_alert_end_actions.length}
              </span>
            )}
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-6">
          {activeTab === 'detection' && (
            <>
              {/* Basic info */}
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-400 mb-2">
                    Rule Name
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                    placeholder="Cat on Counter Alert"
                    className="input-field"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-2">
                    Camera
                  </label>
                  <select
                    value={formData.camera_id}
                    onChange={e => setFormData({ ...formData, camera_id: e.target.value })}
                    className="input-field"
                    required
                  >
                    {cameras.map(cam => (
                      <option key={cam.id} value={cam.id}>{cam.name}</option>
                    ))}
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-2">
                    Condition Type
                  </label>
                  <select
                    value={formData.condition_type}
                    onChange={e => setFormData({ ...formData, condition_type: e.target.value })}
                    className="input-field"
                  >
                    {CONDITION_TYPES.map(ct => (
                      <option key={ct.value} value={ct.value}>{ct.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              
              {/* Detection targets */}
              <div className="p-4 bg-midnight-800/50 rounded-xl space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium flex items-center gap-2">
                    <Settings className="w-4 h-4 text-purrple-400" />
                    Detection Targets
                  </h3>
                  <button
                    type="button"
                    onClick={() => setShowPreview(!showPreview)}
                    className={clsx(
                      "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors",
                      showPreview 
                        ? "bg-purrple-500 text-white"
                        : "bg-midnight-700 hover:bg-midnight-600 text-gray-300"
                    )}
                  >
                    <Eye className="w-4 h-4" />
                    {showPreview ? 'Hide Preview' : 'Preview Detections'}
                  </button>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-2">
                      Primary Target (what to detect)
                    </label>
                    <input
                      type="text"
                      value={formData.primary_target}
                      onChange={e => setFormData({ ...formData, primary_target: e.target.value })}
                      placeholder="cat"
                      className="input-field"
                      required
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Examples: cat, dog, person, hand
                    </p>
                  </div>
                  
                  {needsSecondaryTarget && (
                    <div>
                      <label className="block text-sm text-gray-400 mb-2">
                        Secondary Target (reference object)
                      </label>
                      <input
                        type="text"
                        value={formData.secondary_target}
                        onChange={e => setFormData({ ...formData, secondary_target: e.target.value })}
                        placeholder="counter"
                        className="input-field"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        Examples: counter, table, couch
                      </p>
                    </div>
                  )}
                </div>
                
                {/* Detection Preview */}
                {showPreview && selectedCamera && (
                  <div className="mt-4">
                    <DetectionPreview
                      camera={selectedCamera}
                      prompts={detectionPrompts}
                      confidence={0.5}
                    />
                  </div>
                )}
              </div>
              
              {/* Alert settings */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-2">
                    Alert Message
                  </label>
                  <input
                    type="text"
                    value={formData.alert_message}
                    onChange={e => setFormData({ ...formData, alert_message: e.target.value })}
                    placeholder="🚨 Cat on counter!"
                    className="input-field"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-2">
                    Cooldown (seconds)
                  </label>
                  <input
                    type="number"
                    value={formData.cooldown_seconds}
                    onChange={e => setFormData({ ...formData, cooldown_seconds: parseInt(e.target.value) })}
                    min={0}
                    max={3600}
                    className="input-field"
                  />
                </div>
              </div>
            </>
          )}
          
          {activeTab === 'actions' && (
            <>
              {/* On Alert Start Actions */}
              <div className="p-4 bg-midnight-800/50 rounded-xl space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium flex items-center gap-2">
                    <Bell className="w-4 h-4 text-alert-red" />
                    On Alert Start
                  </h3>
                  <ActionDropdown onSelect={(type) => addAction('start', type)} />
                </div>
                
                {formData.on_alert_start_actions.length === 0 ? (
                  <p className="text-gray-500 text-sm">No actions configured. Add an action to run when alert triggers.</p>
                ) : (
                  <div className="space-y-3">
                    {formData.on_alert_start_actions.map((action, i) => (
                      <ActionEditor
                        key={i}
                        action={action}
                        onUpdate={(key, value) => updateActionParam('start', i, key, value)}
                        onRemove={() => removeAction('start', i)}
                      />
                    ))}
                  </div>
                )}
              </div>
              
              {/* On Alert End Actions */}
              <div className="p-4 bg-midnight-800/50 rounded-xl space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium flex items-center gap-2">
                    <Check className="w-4 h-4 text-alert-green" />
                    On Alert End
                  </h3>
                  <ActionDropdown onSelect={(type) => addAction('end', type)} />
                </div>
                
                {formData.on_alert_end_actions.length === 0 ? (
                  <p className="text-gray-500 text-sm">No actions configured. Add an action to run when alert ends.</p>
                ) : (
                  <div className="space-y-3">
                    {formData.on_alert_end_actions.map((action, i) => (
                      <ActionEditor
                        key={i}
                        action={action}
                        onUpdate={(key, value) => updateActionParam('end', i, key, value)}
                        onRemove={() => removeAction('end', i)}
                      />
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
          
          {/* Enable toggle */}
          <div className="flex items-center gap-3 p-4 bg-midnight-800 rounded-lg">
            <input
              type="checkbox"
              id="rule-enabled"
              checked={formData.enabled}
              onChange={e => setFormData({ ...formData, enabled: e.target.checked })}
              className="w-5 h-5 rounded border-gray-600 text-purrple-500 focus:ring-purrple-500"
            />
            <label htmlFor="rule-enabled" className="font-medium">
              Enable rule immediately
            </label>
          </div>
          
          {/* Submit */}
          <div className="flex gap-3 pt-4">
            <button type="button" onClick={onClose} className="btn-secondary flex-1">
              Cancel
            </button>
            <button type="submit" disabled={saving} className="btn-primary flex-1 flex items-center justify-center gap-2">
              {saving ? <Settings className="w-5 h-5 animate-spin" /> : <Check className="w-5 h-5" />}
              {rule ? 'Save Changes' : 'Create Rule'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ActionDropdown({ onSelect }) {
  const [isOpen, setIsOpen] = useState(false)
  
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 bg-purrple-500 hover:bg-purrple-600 rounded-lg text-sm transition-colors"
      >
        <Plus className="w-4 h-4" />
        Add Action
      </button>
      
      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 top-full mt-2 w-64 bg-midnight-800 border border-midnight-600 rounded-xl shadow-xl z-50 overflow-hidden">
            {ACTION_TYPES.map(action => (
              <button
                key={action.type}
                type="button"
                onClick={() => {
                  onSelect(action.type)
                  setIsOpen(false)
                }}
                className="w-full px-4 py-3 text-left hover:bg-midnight-700 transition-colors flex items-center gap-3"
              >
                <action.icon className="w-5 h-5 text-purrple-400" />
                <div>
                  <div className="font-medium">{action.label}</div>
                  <div className="text-xs text-gray-500">{action.description}</div>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function ActionEditor({ action, onUpdate, onRemove }) {
  const actionDef = ACTION_TYPES.find(a => a.type === action.type)
  const Icon = actionDef?.icon || Settings
  
  return (
    <div className="p-3 bg-midnight-700 rounded-lg">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-purrple-400" />
          <span className="font-medium">{actionDef?.label || action.type}</span>
        </div>
        <button
          type="button"
          onClick={onRemove}
          className="p-1 hover:bg-midnight-600 rounded transition-colors text-gray-400 hover:text-red-400"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      
      <div className="grid grid-cols-2 gap-3">
        {actionDef?.params?.map(param => (
          <div key={param.key}>
            <label className="block text-xs text-gray-400 mb-1">{param.label}</label>
            {param.type === 'select' ? (
              <select
                value={action.params?.[param.key] || param.default}
                onChange={e => onUpdate(param.key, e.target.value)}
                className="input-field text-sm py-1.5"
              >
                {param.options.map(opt => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : param.type === 'number' ? (
              <input
                type="number"
                value={action.params?.[param.key] || param.default}
                onChange={e => onUpdate(param.key, parseInt(e.target.value))}
                className="input-field text-sm py-1.5"
              />
            ) : (
              <input
                type="text"
                value={action.params?.[param.key] || param.default}
                onChange={e => onUpdate(param.key, e.target.value)}
                placeholder={param.default}
                className="input-field text-sm py-1.5"
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function PresetModal({ presets, cameras, onClose, onApply }) {
  const [selectedCamera, setSelectedCamera] = useState(cameras[0]?.id || '')
  
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="glass-card w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Zap className="w-5 h-5 text-purrple-400" />
            Quick Presets
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-midnight-700 rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-400 mb-2">
            Apply to Camera
          </label>
          <select
            value={selectedCamera}
            onChange={e => setSelectedCamera(e.target.value)}
            className="input-field"
          >
            {cameras.map(cam => (
              <option key={cam.id} value={cam.id}>{cam.name}</option>
            ))}
          </select>
        </div>
        
        <div className="space-y-3">
          {presets.map(preset => (
            <button
              key={preset.id}
              onClick={() => onApply(preset.id, selectedCamera)}
              className="w-full p-4 bg-midnight-800/50 hover:bg-midnight-700/50 rounded-xl text-left transition-colors group"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold group-hover:text-purrple-400 transition-colors">
                    {preset.name}
                  </h3>
                  <p className="text-sm text-gray-500">{preset.description}</p>
                </div>
                <Plus className="w-5 h-5 text-gray-500 group-hover:text-purrple-400" />
              </div>
            </button>
          ))}
        </div>
        
        <button onClick={onClose} className="btn-secondary w-full mt-6">
          Close
        </button>
      </div>
    </div>
  )
}
