import { useCallback, useEffect, useRef, useState } from 'react'
import {
  CheckCircle,
  Clipboard,
  ClipboardCheck,
  ExternalLink,
  GitBranch,
  Loader,
  Network,
  Plus,
  Power,
  RefreshCw,
  Server,
  Settings,
  Shield,
  Trash2,
  XCircle,
  Zap,
} from 'lucide-react'
import {
  fetchCopilotToken,
  fetchSetupConfig,
  fetchMcpServers,
  pollGitHubDeviceFlow,
  saveSetupConfig,
  startGitHubDeviceFlow,
  testCopilot,
  testLMStudio,
  addMcpServer,
  removeMcpServer,
  toggleMcpServer,
  reloadMcpServers,
  type AddMcpServerRequest,
  type CopilotTestResponse,
  type CopilotTokenResponse,
  type DeviceCodeResponse,
  type McpServerStatus,
  type SetupConfig,
} from '../api'

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function SectionCard({
  icon,
  title,
  subtitle,
  children,
}: {
  icon: React.ReactNode
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <div className="setup-card">
      <div className="setup-card-header">
        <span className="setup-card-icon">{icon}</span>
        <div>
          <h3 className="setup-card-title">{title}</h3>
          {subtitle && <p className="setup-card-subtitle">{subtitle}</p>}
        </div>
      </div>
      <div className="setup-card-body">{children}</div>
    </div>
  )
}

function StatusBadge({ ok, label }: { ok: boolean | null; label: string }) {
  if (ok === null)
    return <span className="setup-badge setup-badge--idle">{label}</span>
  return ok ? (
    <span className="setup-badge setup-badge--ok">
      <CheckCircle size={12} /> {label}
    </span>
  ) : (
    <span className="setup-badge setup-badge--err">
      <XCircle size={12} /> {label}
    </span>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <button className="setup-copy-btn" onClick={copy} title="Copy to clipboard">
      {copied ? <ClipboardCheck size={14} /> : <Clipboard size={14} />}
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Provider selection section
// ─────────────────────────────────────────────────────────────────────────────

function ProviderSection({
  activeProvider,
  onSelect,
  saving,
}: {
  activeProvider: SetupConfig['llm_provider']
  onSelect: (p: SetupConfig['llm_provider']) => void
  saving: boolean
}) {
  const tiles: { id: SetupConfig['llm_provider']; icon: React.ReactNode; name: string; desc: string }[] = [
    { id: 'lm_studio',  icon: <Server size={22} className="provider-tile-icon" />,  name: 'LM Studio',       desc: 'Local · OpenAI-compatible' },
    { id: 'ollama',     icon: <Power size={22} className="provider-tile-icon" />,   name: 'Ollama',          desc: 'Local · llama3, mistral…' },
    { id: 'openai',     icon: <Zap size={22} className="provider-tile-icon" />,     name: 'OpenAI',          desc: 'Cloud · GPT-4o, o3…' },
    { id: 'groq',       icon: <Zap size={22} className="provider-tile-icon" />,     name: 'Groq',            desc: 'Cloud · Llama 3 ultra-fast' },
    { id: 'anthropic',  icon: <Shield size={22} className="provider-tile-icon" />,  name: 'Anthropic',       desc: 'Cloud · Claude 3.5 / 4' },
    { id: 'copilot',    icon: <GitBranch size={22} className="provider-tile-icon" />, name: 'GitHub Copilot', desc: 'Cloud · GPT-4o, Claude & more' },
  ]

  return (
    <SectionCard
      icon={<Settings size={18} />}
      title="Model Provider"
      subtitle="Choose the language model backend for ECHO"
    >
      <div className="provider-tiles">
        {tiles.map((t) => (
          <button
            key={t.id}
            className={`provider-tile${activeProvider === t.id ? ' provider-tile--active' : ''}`}
            onClick={() => onSelect(t.id)}
            disabled={saving}
          >
            {t.icon}
            <div className="provider-tile-info">
              <span className="provider-tile-name">{t.name}</span>
              <span className="provider-tile-desc">{t.desc}</span>
            </div>
            {activeProvider === t.id && <CheckCircle size={15} className="provider-tile-check" />}
          </button>
        ))}
      </div>
    </SectionCard>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// LM Studio section
// ─────────────────────────────────────────────────────────────────────────────

function LMStudioSection({
  config,
  onSave,
}: {
  config: SetupConfig
  onSave: (updates: Partial<SetupConfig>) => Promise<void>
}) {
  const [baseUrl, setBaseUrl] = useState(config.lm_studio_base_url)
  const [model, setModel] = useState(config.lm_studio_model)
  const [embedModel, setEmbedModel] = useState(config.lm_studio_embedding_model)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState<{
    ok: boolean
    models?: string[]
    error?: string
  } | null>(null)

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await testLMStudio(baseUrl)
      setTestResult(r)
    } catch (e) {
      setTestResult({ ok: false, error: String(e) })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave({
        lm_studio_base_url: baseUrl,
        lm_studio_model: model,
        lm_studio_embedding_model: embedModel,
      })
    } finally {
      setSaving(false)
    }
  }

  const dirty =
    baseUrl !== config.lm_studio_base_url ||
    model !== config.lm_studio_model ||
    embedModel !== config.lm_studio_embedding_model

  return (
    <SectionCard
      icon={<Server size={18} />}
      title="LM Studio"
      subtitle="Configure the local language model provider"
    >
      <div className="setup-field-group">
        <label className="setup-label">API Base URL</label>
        <div className="setup-input-row">
          <input
            className="setup-input"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://localhost:1234/v1"
          />
          <button className="setup-btn setup-btn--secondary" onClick={handleTest} disabled={testing}>
            {testing ? <Loader size={14} className="spin" /> : <RefreshCw size={14} />}
            Test
          </button>
        </div>
        {testResult && (
          <div className={`setup-test-result ${testResult.ok ? 'ok' : 'err'}`}>
            {testResult.ok ? (
              <>
                <CheckCircle size={14} />
                <span>Connected — {testResult.models?.length ?? 0} model(s) loaded</span>
                {testResult.models && testResult.models.length > 0 && (
                  <div className="setup-model-list">
                    {testResult.models.map((m) => (
                      <span key={m} className="setup-model-tag">
                        {m}
                      </span>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <>
                <XCircle size={14} />
                <span>{testResult.error}</span>
              </>
            )}
          </div>
        )}
      </div>

      <div className="setup-field-group">
        <label className="setup-label">Chat Model</label>
        <input
          className="setup-input"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="model-name"
        />
      </div>

      <div className="setup-field-group">
        <label className="setup-label">Embedding Model</label>
        <input
          className="setup-input"
          value={embedModel}
          onChange={(e) => setEmbedModel(e.target.value)}
          placeholder="embedding-model-name"
        />
      </div>

      <div className="setup-actions">
        <button
          className="setup-btn setup-btn--primary"
          onClick={handleSave}
          disabled={!dirty || saving}
        >
          {saving ? <Loader size={14} className="spin" /> : <Settings size={14} />}
          Save Changes
        </button>
        {!dirty && (
          <span className="setup-saved-label">
            <CheckCircle size={12} /> Saved
          </span>
        )}
      </div>
    </SectionCard>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Generic API-key + model section (reused by OpenAI / Groq / Anthropic)
// ─────────────────────────────────────────────────────────────────────────────

function ApiKeySection({
  icon,
  title,
  subtitle,
  apiKeyLabel,
  apiKeyPlaceholder,
  apiKeyValue,
  modelLabel,
  modelValue,
  modelPlaceholder,
  modelSuggestions,
  extraFields,
  onSave,
}: {
  icon: React.ReactNode
  title: string
  subtitle: string
  apiKeyLabel: string
  apiKeyPlaceholder: string
  apiKeyValue: string
  modelLabel: string
  modelValue: string
  modelPlaceholder: string
  modelSuggestions: string[]
  extraFields?: React.ReactNode
  onSave: (apiKey: string, model: string) => Promise<void>
}) {
  const [apiKey, setApiKey] = useState(apiKeyValue === '***' ? '' : apiKeyValue)
  const [model, setModel] = useState(modelValue)
  const [saving, setSaving] = useState(false)
  const dirty = (apiKey !== '' && apiKey !== apiKeyValue) || model !== modelValue

  const handleSave = async () => {
    setSaving(true)
    try { await onSave(apiKey, model) } finally { setSaving(false) }
  }

  const listId = `model-list-${title.replace(/\s/g, '-').toLowerCase()}`

  return (
    <SectionCard icon={icon} title={title} subtitle={subtitle}>
      <div className="setup-field-group">
        <label className="setup-label">{apiKeyLabel}</label>
        <input
          className="setup-input"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={apiKeyPlaceholder}
          autoComplete="off"
        />
        {apiKeyValue === '***' && (
          <p className="setup-mcp-hint" style={{ color: '#10b981' }}>
            <CheckCircle size={11} style={{ display: 'inline', marginRight: 4 }} />
            API key is stored — enter a new one to update
          </p>
        )}
      </div>

      <div className="setup-field-group">
        <label className="setup-label">{modelLabel}</label>
        <input
          className="setup-input"
          list={listId}
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder={modelPlaceholder}
        />
        <datalist id={listId}>
          {modelSuggestions.map((m) => <option key={m} value={m} />)}
        </datalist>
      </div>

      {extraFields}

      <div className="setup-actions">
        <button
          className="setup-btn setup-btn--primary"
          onClick={handleSave}
          disabled={!dirty || saving}
        >
          {saving ? <Loader size={14} className="spin" /> : <Settings size={14} />}
          Save Changes
        </button>
        {!dirty && apiKeyValue === '***' && (
          <span className="setup-saved-label"><CheckCircle size={12} /> Saved</span>
        )}
      </div>
    </SectionCard>
  )
}

function OpenAISection({ config, onSave }: { config: SetupConfig; onSave: (u: Partial<SetupConfig>) => Promise<void> }) {
  const [baseUrl, setBaseUrl] = useState(config.openai_base_url)
  return (
    <ApiKeySection
      icon={<Zap size={18} />}
      title="OpenAI"
      subtitle="Connect to OpenAI or any OpenAI-compatible endpoint"
      apiKeyLabel="API Key"
      apiKeyPlaceholder="sk-..."
      apiKeyValue={config.openai_api_key}
      modelLabel="Model"
      modelValue={config.openai_model}
      modelPlaceholder="gpt-4o-mini"
      modelSuggestions={['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini', 'o3', 'o3-mini', 'o4-mini']}
      extraFields={
        <div className="setup-field-group">
          <label className="setup-label">Base URL</label>
          <input
            className="setup-input"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
          />
          <p className="setup-mcp-hint">Change to use any OpenAI-compatible endpoint</p>
        </div>
      }
      onSave={async (apiKey, model) => {
        await onSave({ openai_api_key: apiKey || undefined, openai_model: model, openai_base_url: baseUrl })
      }}
    />
  )
}

function GroqSection({ config, onSave }: { config: SetupConfig; onSave: (u: Partial<SetupConfig>) => Promise<void> }) {
  return (
    <ApiKeySection
      icon={<Zap size={18} />}
      title="Groq"
      subtitle="Ultra-fast inference — free tier available at console.groq.com"
      apiKeyLabel="API Key"
      apiKeyPlaceholder="gsk_..."
      apiKeyValue={config.groq_api_key}
      modelLabel="Model"
      modelValue={config.groq_model}
      modelPlaceholder="llama-3.3-70b-versatile"
      modelSuggestions={['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'llama-3.2-90b-vision-preview', 'mixtral-8x7b-32768', 'gemma2-9b-it']}
      onSave={async (apiKey, model) => {
        await onSave({ groq_api_key: apiKey || undefined, groq_model: model })
      }}
    />
  )
}

function AnthropicSection({ config, onSave }: { config: SetupConfig; onSave: (u: Partial<SetupConfig>) => Promise<void> }) {
  return (
    <ApiKeySection
      icon={<Shield size={18} />}
      title="Anthropic"
      subtitle="Claude models — get your key at console.anthropic.com"
      apiKeyLabel="API Key"
      apiKeyPlaceholder="sk-ant-..."
      apiKeyValue={config.anthropic_api_key}
      modelLabel="Model"
      modelValue={config.anthropic_model}
      modelPlaceholder="claude-3-5-haiku-20241022"
      modelSuggestions={['claude-3-5-haiku-20241022', 'claude-3-5-sonnet-20241022', 'claude-opus-4-5', 'claude-sonnet-4-5']}
      onSave={async (apiKey, model) => {
        await onSave({ anthropic_api_key: apiKey || undefined, anthropic_model: model })
      }}
    />
  )
}

function OllamaSection({ config, onSave }: { config: SetupConfig; onSave: (u: Partial<SetupConfig>) => Promise<void> }) {
  const [baseUrl, setBaseUrl] = useState(config.ollama_base_url)
  const [model, setModel] = useState(config.ollama_chat_model)
  const [saving, setSaving] = useState(false)
  const dirty = baseUrl !== config.ollama_base_url || model !== config.ollama_chat_model

  return (
    <SectionCard icon={<Power size={18} />} title="Ollama" subtitle="Local models via Ollama daemon — ollama.ai">
      <div className="setup-field-group">
        <label className="setup-label">Ollama Base URL</label>
        <input
          className="setup-input"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="http://localhost:11434"
        />
      </div>
      <div className="setup-field-group">
        <label className="setup-label">Chat Model</label>
        <input
          className="setup-input"
          list="ollama-models-list"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="llama3.2"
        />
        <datalist id="ollama-models-list">
          {['llama3.2', 'llama3.1', 'mistral', 'gemma3', 'qwen2.5', 'phi4', 'deepseek-r1'].map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        <p className="setup-mcp-hint">Run <code>ollama pull &lt;model&gt;</code> first</p>
      </div>
      <div className="setup-actions">
        <button
          className="setup-btn setup-btn--primary"
          onClick={async () => {
            setSaving(true)
            try { await onSave({ ollama_base_url: baseUrl, ollama_chat_model: model }) }
            finally { setSaving(false) }
          }}
          disabled={!dirty || saving}
        >
          {saving ? <Loader size={14} className="spin" /> : <Settings size={14} />}
          Save Changes
        </button>
        {!dirty && <span className="setup-saved-label"><CheckCircle size={12} /> Saved</span>}
      </div>
    </SectionCard>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// GitHub device flow section
// ─────────────────────────────────────────────────────────────────────────────

type DeviceFlowStage =
  | 'idle'
  | 'start-loading'
  | 'awaiting-user'
  | 'polling'
  | 'success'
  | 'error'

function GitHubSection({
  config,
  onSave,
}: {
  config: SetupConfig
  onSave: (updates: Partial<SetupConfig>) => Promise<void>
}) {
  const COPILOT_MODELS = ['gpt-4o', 'gpt-4.1', 'claude-3.5-sonnet', 'o1', 'o3-mini']
  const [copilotModel, setCopilotModel] = useState(config.copilot_model)
  const [savingModel, setSavingModel] = useState(false)
  const [stage, setStage] = useState<DeviceFlowStage>('idle')
  const [deviceCode, setDeviceCode] = useState<DeviceCodeResponse | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [copilotToken, setCopilotToken] = useState<CopilotTokenResponse | null>(null)
  const [fetchingCopilot, setFetchingCopilot] = useState(false)
  const [hasToken, setHasToken] = useState(config.has_github_token)
  const [testingCopilot, setTestingCopilot] = useState(false)
  const [copilotTestResult, setCopilotTestResult] = useState<CopilotTestResponse | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollIntervalSec = useRef(5)

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  // cleanup on unmount
  useEffect(() => () => stopPolling(), [stopPolling])

  const startPoll = useCallback(
    (dc: DeviceCodeResponse) => {
      pollIntervalSec.current = dc.interval ?? 5
      setStage('polling')

      pollRef.current = setInterval(async () => {
        try {
          const res = await pollGitHubDeviceFlow(dc.device_code)

          if (res.access_token) {
            stopPolling()
            await saveSetupConfig({ github_token: res.access_token })
            await onSave({}) // refresh parent config
            setHasToken(true)
            setStage('success')
          } else if (res.error === 'slow_down') {
            pollIntervalSec.current += 5
          } else if (
            res.error === 'expired_token' ||
            res.error === 'access_denied'
          ) {
            stopPolling()
            setErrorMsg(res.error_description ?? res.error ?? 'Flow expired')
            setStage('error')
          }
          // 'authorization_pending' → keep polling
        } catch (err) {
          stopPolling()
          setErrorMsg(String(err))
          setStage('error')
        }
      }, pollIntervalSec.current * 1000)
    },
    [stopPolling, onSave],
  )

  const handleStart = async () => {
    setStage('start-loading')
    setErrorMsg('')
    try {
      const dc = await startGitHubDeviceFlow()
      setDeviceCode(dc)
      setStage('awaiting-user')
    } catch (err) {
      setErrorMsg(String(err))
      setStage('error')
    }
  }

  const handleAuthorized = () => {
    if (!deviceCode) return
    startPoll(deviceCode)
  }

  const handleReset = () => {
    stopPolling()
    setStage('idle')
    setDeviceCode(null)
    setErrorMsg('')
  }

  const handleGetCopilotToken = async () => {
    setFetchingCopilot(true)
    setCopilotToken(null)
    try {
      const t = await fetchCopilotToken()
      setCopilotToken(t)
    } catch (err) {
      setErrorMsg(String(err))
    } finally {
      setFetchingCopilot(false)
    }
  }

  const handleTestCopilot = async () => {
    setTestingCopilot(true)
    setCopilotTestResult(null)
    try {
      const result = await testCopilot()
      setCopilotTestResult(result)
    } catch (err) {
      setCopilotTestResult({ ok: false, error: String(err) })
    } finally {
      setTestingCopilot(false)
    }
  }

  return (
    <SectionCard
      icon={<GitBranch size={18} />}
      title="GitHub Integration"
      subtitle="Sign in like VS Code — no OAuth App setup required"
    >
      {/* Copilot model selector */}
      <div className="setup-field-group">
        <label className="setup-label">Copilot Model</label>
        <div className="setup-input-row">
          <input
            className="setup-input"
            list="copilot-models-list"
            value={copilotModel}
            onChange={(e) => setCopilotModel(e.target.value)}
            placeholder="gpt-4o"
          />
          <datalist id="copilot-models-list">
            {COPILOT_MODELS.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <button
            className="setup-btn setup-btn--secondary"
            onClick={async () => {
              setSavingModel(true)
              try { await onSave({ copilot_model: copilotModel }) }
              finally { setSavingModel(false) }
            }}
            disabled={savingModel || copilotModel === config.copilot_model}
          >
            {savingModel ? <Loader size={14} className="spin" /> : <Settings size={14} />}
            Save
          </button>
        </div>
      </div>

      {/* Status + action area */}
      {stage === 'idle' && (
        <button
          className="setup-btn setup-btn--primary setup-btn--github"
          onClick={handleStart}
        >
          <GitBranch size={15} />
          Sign in with GitHub
        </button>
      )}

      {stage === 'start-loading' && (
        <div className="setup-loading-row">
          <Loader size={16} className="spin" />
          Requesting device code from GitHub…
        </div>
      )}

      {stage === 'awaiting-user' && deviceCode && (
        <div className="setup-device-flow-box">
          <p className="setup-device-instructions">
            Visit the URL below and enter the code to authorize ECHO:
          </p>

          <div className="setup-device-row">
            <a
              href={deviceCode.verification_uri}
              target="_blank"
              rel="noreferrer"
              className="setup-verification-url"
            >
              {deviceCode.verification_uri}
              <ExternalLink size={12} />
            </a>
          </div>

          <div className="setup-user-code-box">
            <span className="setup-user-code">{deviceCode.user_code}</span>
            <CopyButton text={deviceCode.user_code} />
          </div>

          <div className="setup-device-actions">
            <button className="setup-btn setup-btn--primary" onClick={handleAuthorized}>
              <CheckCircle size={14} />
              I've authorized — start polling
            </button>
            <button className="setup-btn setup-btn--ghost" onClick={handleReset}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {stage === 'polling' && (
        <div className="setup-polling-row">
          <Loader size={16} className="spin" />
          <span>Waiting for GitHub authorization…</span>
          <button className="setup-btn setup-btn--ghost setup-btn--sm" onClick={handleReset}>
            Cancel
          </button>
        </div>
      )}

      {stage === 'success' && (
        <div className="setup-success-box">
          <CheckCircle size={18} />
          <div>
            <strong>GitHub Connected</strong>
            <p>OAuth token stored in .env</p>
          </div>
          <button className="setup-btn setup-btn--ghost setup-btn--sm" onClick={handleReset}>
            <RefreshCw size={13} /> Re-authenticate
          </button>
        </div>
      )}

      {stage === 'error' && (
        <div className="setup-error-box">
          <XCircle size={16} />
          <span>{errorMsg}</span>
          <button className="setup-btn setup-btn--ghost setup-btn--sm" onClick={handleReset}>
            Try again
          </button>
        </div>
      )}

      {/* Already authenticated banner */}
      {hasToken && stage === 'idle' && (
        <div className="setup-already-authed">
          <CheckCircle size={14} />
          <span>GitHub token is stored in .env</span>
        </div>
      )}

      {/* Copilot token sub-section */}
      {(hasToken || stage === 'success') && (
        <div className="setup-copilot-section">
          <div className="setup-copilot-header">
            <Zap size={14} />
            <span>GitHub Copilot Token</span>
          </div>
          <p className="setup-copilot-desc">
            Exchange your GitHub token for a short-lived Copilot API token
            (valid ~30 min) to use Copilot as ECHO's language model.
          </p>
          <button
            className="setup-btn setup-btn--accent"
            onClick={handleGetCopilotToken}
            disabled={fetchingCopilot}
          >
            {fetchingCopilot ? (
              <Loader size={14} className="spin" />
            ) : (
              <Shield size={14} />
            )}
            Get Copilot Token
          </button>

          <button
            className="setup-btn setup-btn--secondary"
            onClick={handleTestCopilot}
            disabled={testingCopilot}
          >
            {testingCopilot ? <Loader size={14} className="spin" /> : <Zap size={14} />}
            Test Connection
          </button>

          {copilotTestResult && (
            <div className={`setup-test-result ${copilotTestResult.ok ? 'ok' : 'err'}`}>
              {copilotTestResult.ok ? (
                <>
                  <CheckCircle size={14} />
                  <span>Connected — model: {copilotTestResult.model}</span>
                </>
              ) : (
                <>
                  <XCircle size={14} />
                  <span>{copilotTestResult.error}</span>
                </>
              )}
            </div>
          )}

          {copilotToken && (
            <div className="setup-copilot-result">
              <div className="setup-field-group">
                <label className="setup-label">API Endpoint</label>
                <div className="setup-code-row">
                  <code className="setup-code">{copilotToken.endpoint}</code>
                  <CopyButton text={copilotToken.endpoint} />
                </div>
              </div>
              <div className="setup-field-group">
                <label className="setup-label">Token</label>
                <div className="setup-code-row">
                  <code className="setup-code setup-code--token">
                    {copilotToken.token.slice(0, 24)}…
                  </code>
                  <CopyButton text={copilotToken.token} />
                </div>
              </div>
              <p className="setup-copilot-expires">
                Expires: {new Date(copilotToken.expires_at).toLocaleTimeString()}
              </p>
              <p className="setup-copilot-hint">
                Tip: set <strong>LM_STUDIO_BASE_URL</strong> to the endpoint above and{' '}
                <strong>LM_STUDIO_API_KEY</strong> to the token to use Copilot as your
                model provider.
              </p>
            </div>
          )}
        </div>
      )}
    </SectionCard>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MCP Section
// ─────────────────────────────────────────────────────────────────────────────

function MCPSection() {
  const [servers, setServers] = useState<McpServerStatus[]>([])
  const [loadingServers, setLoadingServers] = useState(true)
  const [reloading, setReloading] = useState(false)
  const [toggling, setToggling] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)

  // Add-server form state
  const [showAddForm, setShowAddForm] = useState(false)
  const [addTransport, setAddTransport] = useState<'stdio' | 'sse'>('stdio')
  const [addName, setAddName] = useState('')
  const [addCommand, setAddCommand] = useState('')
  const [addArgs, setAddArgs] = useState('')
  const [addUrl, setAddUrl] = useState('')
  const [addDesc, setAddDesc] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState('')

  const load = useCallback(async () => {
    try {
      const s = await fetchMcpServers()
      setServers(s)
    } catch {
      // keep empty
    } finally {
      setLoadingServers(false)
    }
  }, [])

  // Poll while any enabled server is still connecting (up to 20 s after mount)
  useEffect(() => {
    load()
    const deadline = Date.now() + 20_000
    const id = setInterval(async () => {
      if (Date.now() > deadline) { clearInterval(id); return }
      try {
        const s = await fetchMcpServers()
        setServers(s)
        const stillConnecting = s.some((x) => x.enabled && !x.connected)
        if (!stillConnecting) clearInterval(id)
      } catch {
        clearInterval(id)
      }
    }, 2_000)
    return () => clearInterval(id)
  }, [load])

  const handleReload = async () => {
    setReloading(true)
    try {
      setServers(await reloadMcpServers())
    } finally {
      setReloading(false)
    }
  }

  const handleToggle = async (name: string, currentEnabled: boolean) => {
    setToggling(name)
    try {
      const updated = await toggleMcpServer(name, !currentEnabled)
      setServers((s) => s.map((x) => (x.name === name ? updated : x)))
    } catch {
      // ignore
    } finally {
      setToggling(null)
    }
  }

  const handleRemove = async (name: string) => {
    setRemoving(name)
    try {
      await removeMcpServer(name)
      setServers((s) => s.filter((x) => x.name !== name))
    } catch {
      // ignore
    } finally {
      setRemoving(null)
    }
  }

  const resetAddForm = () => {
    setAddName('')
    setAddCommand('')
    setAddArgs('')
    setAddUrl('')
    setAddDesc('')
    setAddError('')
    setShowAddForm(false)
  }

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!addName.trim()) return
    setAdding(true)
    setAddError('')
    try {
      const args = addArgs
        .trim()
        .split(/\s+/)
        .filter(Boolean)
      const req: AddMcpServerRequest = {
        name: addName.trim(),
        transport: addTransport,
        description: addDesc.trim() || undefined,
        ...(addTransport === 'stdio'
          ? { command: addCommand.trim(), args }
          : { url: addUrl.trim() }),
      }
      const server = await addMcpServer(req)
      setServers((s) => [...s.filter((x) => x.name !== server.name), server])
      resetAddForm()
    } catch (err) {
      setAddError(String(err))
    } finally {
      setAdding(false)
    }
  }

  const connectedCount = servers.filter((s) => s.connected).length
  const totalTools = servers.reduce((n, s) => n + s.tool_count, 0)

  return (
    <SectionCard
      icon={<Network size={18} />}
      title="MCP Servers"
      subtitle="Model Context Protocol — connect external tools and data sources to ECHO"
    >
      {/* Top bar: stats + reload */}
      <div className="setup-mcp-topbar">
        <div className="setup-mcp-stats">
          {!loadingServers && servers.length > 0 && (
            <>
              <span
                className={`setup-badge ${connectedCount > 0 ? 'setup-badge--ok' : 'setup-badge--idle'}`}
              >
                {connectedCount}/{servers.length} connected
              </span>
              {totalTools > 0 && (
                <span className="setup-badge setup-badge--ok">
                  {totalTools} tool{totalTools !== 1 ? 's' : ''}
                </span>
              )}
            </>
          )}
        </div>
        <button
          className="setup-btn setup-btn--ghost setup-btn--sm"
          onClick={handleReload}
          disabled={reloading}
          title="Reload mcp.json from disk"
        >
          {reloading ? <Loader size={13} className="spin" /> : <RefreshCw size={13} />}
          Reload
        </button>
      </div>

      {/* Server list */}
      {loadingServers ? (
        <div className="setup-loading-row">
          <Loader size={16} className="spin" />
          Loading servers…
        </div>
      ) : servers.length === 0 ? (
        <div className="setup-mcp-empty">
          <Server size={28} />
          <span>No MCP servers configured</span>
          <p>Add a server below or edit <code>data/mcp.json</code> and reload.</p>
        </div>
      ) : (
        <div className="setup-mcp-server-list">
          {servers.map((s) => {
            const state = s.connected ? 'connected' : s.enabled ? 'error' : 'disabled'
            return (
              <div key={s.name} className={`setup-mcp-server setup-mcp-server--${state}`}>
                <div className="setup-mcp-server-header">
                  <div className="setup-mcp-server-info">
                    <span className="setup-mcp-server-name">{s.name}</span>
                    <span className="setup-mcp-transport-badge">{s.transport}</span>
                    {s.connected && s.tool_count > 0 && (
                      <span className="setup-badge setup-badge--ok setup-badge--sm">
                        {s.tool_count} tool{s.tool_count !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                  <div className="setup-mcp-server-actions">
                    <span className={`setup-mcp-status-dot setup-mcp-status-dot--${state}`} />
                    <span className="setup-mcp-status-label">{state}</span>
                    <button
                      className={`setup-btn setup-btn--ghost setup-btn--sm ${!s.enabled ? 'setup-btn--muted' : ''}`}
                      onClick={() => handleToggle(s.name, s.enabled)}
                      disabled={toggling === s.name}
                      title={s.enabled ? 'Disable server' : 'Enable server'}
                    >
                      {toggling === s.name ? (
                        <Loader size={13} className="spin" />
                      ) : (
                        <Power size={13} />
                      )}
                    </button>
                    <button
                      className="setup-btn setup-btn--ghost setup-btn--sm setup-btn--danger"
                      onClick={() => handleRemove(s.name)}
                      disabled={removing === s.name}
                      title="Remove server"
                    >
                      {removing === s.name ? (
                        <Loader size={13} className="spin" />
                      ) : (
                        <Trash2 size={13} />
                      )}
                    </button>
                  </div>
                </div>
                {s.description && (
                  <p className="setup-mcp-server-desc">{s.description}</p>
                )}
                {s.error && s.enabled && !s.connected && (
                  <div className="setup-test-result err setup-mcp-server-error">
                    <XCircle size={13} />
                    <span>{s.error}</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Add server */}
      {!showAddForm ? (
        <button
          className="setup-btn setup-btn--secondary"
          onClick={() => setShowAddForm(true)}
        >
          <Plus size={14} />
          Add Server
        </button>
      ) : (
        <form className="setup-mcp-add-form" onSubmit={handleAdd}>
          <div className="setup-mcp-add-form-title">
            <Plus size={14} />
            New MCP Server
          </div>

          <div className="setup-field-group">
            <label className="setup-label">Name *</label>
            <input
              className="setup-input"
              value={addName}
              onChange={(e) => setAddName(e.target.value)}
              placeholder="e.g. fetch, filesystem, brave"
              required
              autoFocus
            />
          </div>

          <div className="setup-field-group">
            <label className="setup-label">Transport</label>
            <div className="setup-mcp-transport-tabs">
              {(['stdio', 'sse'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`setup-mcp-transport-tab ${addTransport === t ? 'active' : ''}`}
                  onClick={() => setAddTransport(t)}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {addTransport === 'stdio' ? (
            <>
              <div className="setup-field-group">
                <label className="setup-label">Command *</label>
                <input
                  className="setup-input"
                  value={addCommand}
                  onChange={(e) => setAddCommand(e.target.value)}
                  placeholder="e.g. uvx, npx, python"
                  required
                />
              </div>
              <div className="setup-field-group">
                <label className="setup-label">Arguments</label>
                <input
                  className="setup-input"
                  value={addArgs}
                  onChange={(e) => setAddArgs(e.target.value)}
                  placeholder="e.g. mcp-server-fetch  or  @modelcontextprotocol/server-filesystem /tmp"
                />
                <p className="setup-mcp-hint">Space-separated arguments passed to the command</p>
              </div>
            </>
          ) : (
            <div className="setup-field-group">
              <label className="setup-label">URL *</label>
              <input
                className="setup-input"
                value={addUrl}
                onChange={(e) => setAddUrl(e.target.value)}
                placeholder="http://localhost:3001/sse"
                required
              />
            </div>
          )}

          <div className="setup-field-group">
            <label className="setup-label">Description</label>
            <input
              className="setup-input"
              value={addDesc}
              onChange={(e) => setAddDesc(e.target.value)}
              placeholder="Optional description"
            />
          </div>

          {addError && (
            <div className="setup-test-result err">
              <XCircle size={13} />
              <span>{addError}</span>
            </div>
          )}

          <div className="setup-actions">
            <button
              type="submit"
              className="setup-btn setup-btn--primary"
              disabled={adding}
            >
              {adding ? <Loader size={14} className="spin" /> : <Plus size={14} />}
              Add Server
            </button>
            <button
              type="button"
              className="setup-btn setup-btn--ghost"
              onClick={resetAddForm}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </SectionCard>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Root panel
// ─────────────────────────────────────────────────────────────────────────────

export default function SetupPanel() {
  const [config, setConfig] = useState<SetupConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeProvider, setActiveProvider] = useState<SetupConfig['llm_provider']>('lm_studio')
  const [savingProvider, setSavingProvider] = useState(false)

  useEffect(() => {
    fetchSetupConfig()
      .then((cfg) => {
        setConfig(cfg)
        setActiveProvider(cfg.llm_provider)
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async (updates: Partial<SetupConfig>) => {
    await saveSetupConfig(updates)
    // Refresh config (best-effort — UI already reflects selection)
    const fresh = await fetchSetupConfig()
    setConfig(fresh)
  }

  const handleSelectProvider = async (p: SetupConfig['llm_provider']) => {
    if (p === activeProvider || savingProvider) return
    setActiveProvider(p)  // update UI immediately
    setSavingProvider(true)
    try {
      await saveSetupConfig({ llm_provider: p })
      const fresh = await fetchSetupConfig()
      setConfig(fresh)
    } finally {
      setSavingProvider(false)
    }
  }

  if (loading)
    return (
      <div className="setup-loading">
        <Loader size={24} className="spin" />
        Loading configuration…
      </div>
    )

  if (error || !config)
    return (
      <div className="setup-error-full">
        <XCircle size={24} />
        <p>{error || 'Failed to load configuration'}</p>
      </div>
    )

  return (
    <div className="setup-panel">
      <div className="setup-panel-header">
        <Settings size={20} />
        <div>
          <h2 className="setup-panel-title">Setup</h2>
          <p className="setup-panel-subtitle">
            Configure model provider, integrations, and API connections
          </p>
        </div>
        <StatusBadge ok={config.has_github_token} label="GitHub" />
      </div>

      <div className="setup-sections">
        <ProviderSection
          activeProvider={activeProvider}
          onSelect={handleSelectProvider}
          saving={savingProvider}
        />
        {activeProvider === 'lm_studio'  && <LMStudioSection config={config} onSave={handleSave} />}
        {activeProvider === 'openai'      && <OpenAISection config={config} onSave={handleSave} />}
        {activeProvider === 'groq'        && <GroqSection config={config} onSave={handleSave} />}
        {activeProvider === 'anthropic'   && <AnthropicSection config={config} onSave={handleSave} />}
        {activeProvider === 'ollama'      && <OllamaSection config={config} onSave={handleSave} />}
        {/* GitHub section always visible — needed for Copilot auth + device flow */}
        <GitHubSection config={config} onSave={handleSave} />
        <MCPSection />
      </div>
    </div>
  )
}
