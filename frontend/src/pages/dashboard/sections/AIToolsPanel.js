import React, { useState, useEffect } from 'react';
import { apiClient } from '@/lib/apiClient';
import { toast } from 'sonner';

/**
 * AI Tools Panel - Integrated HuggingFace, Fetch.ai, and Flokx tools
 * Displayed as collapsible panels within the Welcome section
 */
export default function AIToolsPanel() {
  const [activeTab, setActiveTab] = useState('huggingface');
  
  // HuggingFace state
  const [hfConfigured, setHfConfigured] = useState(false);
  const [hfTasks, setHfTasks] = useState([]);
  const [hfModels, setHfModels] = useState([]);
  const [hfSelectedTask, setHfSelectedTask] = useState('');
  const [hfSelectedModel, setHfSelectedModel] = useState('');
  const [hfInputText, setHfInputText] = useState('');
  const [hfResult, setHfResult] = useState(null);
  const [hfProcessing, setHfProcessing] = useState(false);
  
  // Fetch.ai state
  const [fetchaiActive, setFetchaiActive] = useState(false);
  const [fetchaiSignals, setFetchaiSignals] = useState([]);
  
  // Flokx state
  const [flokxActive, setFlokxActive] = useState(false);
  const [flokxAlerts, setFlokxAlerts] = useState([]);

  // Check HuggingFace configuration on mount
  useEffect(() => {
    checkHuggingFaceConfig();
  }, []);

  // Load tasks when configured
  useEffect(() => {
    if (hfConfigured) {
      fetchHuggingFaceTasks();
    }
  }, [hfConfigured]);

  // Load models when task changes
  useEffect(() => {
    if (hfSelectedTask && hfConfigured) {
      fetchHuggingFaceModels(hfSelectedTask);
    }
  }, [hfSelectedTask]);

  const checkHuggingFaceConfig = async () => {
    try {
      const response = await apiClient.get('/huggingface/test-connection');
      setHfConfigured(response.data.configured || false);
    } catch (err) {
      console.error('Failed to check HuggingFace config:', err);
      setHfConfigured(false);
    }
  };

  const fetchHuggingFaceTasks = async () => {
    try {
      const response = await apiClient.get('/huggingface/tasks');
      setHfTasks(response.data.tasks || []);
      if (response.data.tasks && response.data.tasks.length > 0) {
        const defaultTask = response.data.tasks.find(t => t === 'text-classification') || response.data.tasks[0];
        setHfSelectedTask(defaultTask);
      }
    } catch (err) {
      console.error('Failed to fetch HuggingFace tasks:', err);
    }
  };

  const fetchHuggingFaceModels = async (task) => {
    try {
      setHfModels([]);
      setHfSelectedModel('');
      const response = await apiClient.get(`/huggingface/models?task=${task}&limit=10`);
      const modelList = response.data.models || [];
      setHfModels(modelList);
      if (modelList.length > 0) {
        setHfSelectedModel(modelList[0].modelId || modelList[0].id || '');
      }
    } catch (err) {
      console.error('Failed to fetch models:', err);
    }
  };

  const handleHuggingFaceAnalyze = async () => {
    if (!hfInputText.trim()) {
      toast.error('Please enter text to analyze');
      return;
    }

    setHfProcessing(true);
    setHfResult(null);

    try {
      let response;
      if (hfSelectedTask === 'text-classification' || hfSelectedTask === 'sentiment-analysis') {
        response = await apiClient.post('/huggingface/analyze-sentiment', {
          text: hfInputText,
          model_id: hfSelectedModel || undefined
        });
      } else if (hfSelectedTask === 'summarization') {
        response = await apiClient.post('/huggingface/summarize', {
          text: hfInputText,
          model_id: hfSelectedModel || undefined
        });
      } else {
        toast.error('Task not yet supported');
        setHfProcessing(false);
        return;
      }

      setHfResult(response.data);
      toast.success('Analysis complete!');
    } catch (err) {
      console.error('Analysis failed:', err);
      toast.error(err.response?.data?.detail || 'Analysis failed');
    } finally {
      setHfProcessing(false);
    }
  };

  return (
    <div style={{
      marginTop: '16px',
      padding: '16px',
      background: 'var(--glass)',
      border: '1px solid var(--line)',
      borderRadius: '8px'
    }}>
      <div style={{
        fontWeight: 700,
        marginBottom: '12px',
        color: 'var(--text)',
        fontSize: '1.1rem'
      }}>
        🧠 AI Tools & Integrations
      </div>

      {/* Tab Navigation */}
      <div style={{
        display: 'flex',
        gap: '8px',
        marginBottom: '16px',
        flexWrap: 'wrap'
      }}>
        <button
          onClick={() => setActiveTab('huggingface')}
          style={{
            padding: '8px 16px',
            background: activeTab === 'huggingface' ? 'var(--accent)' : 'var(--panel)',
            color: 'var(--text)',
            border: '1px solid var(--line)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.9rem'
          }}
        >
          🤗 HuggingFace
        </button>
        <button
          onClick={() => setActiveTab('fetchai')}
          style={{
            padding: '8px 16px',
            background: activeTab === 'fetchai' ? 'var(--accent)' : 'var(--panel)',
            color: 'var(--text)',
            border: '1px solid var(--line)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.9rem'
          }}
        >
          🔮 Fetch.ai
        </button>
        <button
          onClick={() => setActiveTab('flokx')}
          style={{
            padding: '8px 16px',
            background: activeTab === 'flokx' ? 'var(--accent)' : 'var(--panel)',
            color: 'var(--text)',
            border: '1px solid var(--line)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.9rem'
          }}
        >
          🧠 FlokX
        </button>
      </div>

      {/* HuggingFace Panel */}
      {activeTab === 'huggingface' && (
        <div>
          {!hfConfigured ? (
            <div style={{
              padding: '20px',
              textAlign: 'center',
              background: 'var(--panel)',
              borderRadius: '8px',
              border: '1px solid var(--line)'
            }}>
              <div style={{ fontSize: '2rem', marginBottom: '12px' }}>🤗</div>
              <p style={{ color: 'var(--muted)', marginBottom: '12px' }}>
                HuggingFace API key not configured
              </p>
              <button
                onClick={() => window.location.hash = '#/dashboard?section=api'}
                style={{
                  padding: '8px 16px',
                  background: 'var(--accent2)',
                  color: 'var(--text)',
                  border: 'none',
                  borderRadius: '6px',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Configure API Key
              </button>
            </div>
          ) : (
            <div>
              {/* Task Selection */}
              <div style={{ marginBottom: '12px' }}>
                <label style={{
                  display: 'block',
                  marginBottom: '4px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: 'var(--text)'
                }}>
                  Task
                </label>
                <select
                  value={hfSelectedTask}
                  onChange={(e) => setHfSelectedTask(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px',
                    background: 'var(--panel)',
                    border: '1px solid var(--line)',
                    borderRadius: '6px',
                    color: 'var(--text)',
                    fontSize: '0.9rem'
                  }}
                >
                  {hfTasks.map(task => (
                    <option key={task} value={task}>
                      {task.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </option>
                  ))}
                </select>
              </div>

              {/* Model Selection */}
              {hfModels.length > 0 && (
                <div style={{ marginBottom: '12px' }}>
                  <label style={{
                    display: 'block',
                    marginBottom: '4px',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    color: 'var(--text)'
                  }}>
                    Model (optional)
                  </label>
                  <select
                    value={hfSelectedModel}
                    onChange={(e) => setHfSelectedModel(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px',
                      background: 'var(--panel)',
                      border: '1px solid var(--line)',
                      borderRadius: '6px',
                      color: 'var(--text)',
                      fontSize: '0.9rem'
                    }}
                  >
                    <option value="">Default</option>
                    {hfModels.map(model => (
                      <option key={model.modelId || model.id} value={model.modelId || model.id}>
                        {model.modelId || model.id}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Input Text */}
              <div style={{ marginBottom: '12px' }}>
                <label style={{
                  display: 'block',
                  marginBottom: '4px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: 'var(--text)'
                }}>
                  Text
                </label>
                <textarea
                  value={hfInputText}
                  onChange={(e) => setHfInputText(e.target.value)}
                  placeholder={
                    hfSelectedTask === 'summarization'
                      ? 'Enter text to summarize...'
                      : 'Enter text for analysis...'
                  }
                  style={{
                    width: '100%',
                    minHeight: '100px',
                    padding: '8px',
                    background: 'var(--panel)',
                    border: '1px solid var(--line)',
                    borderRadius: '6px',
                    color: 'var(--text)',
                    fontSize: '0.9rem',
                    fontFamily: 'inherit',
                    resize: 'vertical'
                  }}
                />
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                <button
                  onClick={handleHuggingFaceAnalyze}
                  disabled={hfProcessing || !hfInputText.trim()}
                  style={{
                    padding: '8px 16px',
                    background: hfProcessing ? 'var(--muted)' : 'var(--success)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    fontWeight: 600,
                    cursor: hfProcessing ? 'not-allowed' : 'pointer',
                    fontSize: '0.9rem',
                    flex: 1
                  }}
                >
                  {hfProcessing ? '⏳ Processing...' : '✨ Analyze'}
                </button>
                <button
                  onClick={() => { setHfInputText(''); setHfResult(null); }}
                  disabled={hfProcessing}
                  style={{
                    padding: '8px 16px',
                    background: 'var(--panel)',
                    color: 'var(--text)',
                    border: '1px solid var(--line)',
                    borderRadius: '6px',
                    fontWeight: 600,
                    cursor: hfProcessing ? 'not-allowed' : 'pointer',
                    fontSize: '0.9rem'
                  }}
                >
                  Clear
                </button>
              </div>

              {/* Results */}
              {hfResult && (
                <div style={{
                  padding: '12px',
                  background: 'var(--panel)',
                  border: '1px solid var(--success)',
                  borderRadius: '6px'
                }}>
                  <div style={{
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    color: 'var(--text)',
                    marginBottom: '8px'
                  }}>
                    Results
                  </div>
                  
                  {hfResult.label && (
                    <div>
                      <span style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>Sentiment: </span>
                      <span style={{
                        fontWeight: 600,
                        color: hfResult.label === 'POSITIVE' ? 'var(--success)' :
                              hfResult.label === 'NEGATIVE' ? 'var(--error)' :
                              'var(--warning)'
                      }}>
                        {hfResult.label}
                        {hfResult.score && ` (${(hfResult.score * 100).toFixed(1)}%)`}
                      </span>
                    </div>
                  )}
                  
                  {hfResult.summary_text && (
                    <div style={{
                      padding: '8px',
                      background: 'var(--glass)',
                      borderRadius: '4px',
                      color: 'var(--text)',
                      fontSize: '0.85rem',
                      lineHeight: '1.5'
                    }}>
                      {hfResult.summary_text}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Fetch.ai Panel */}
      {activeTab === 'fetchai' && (
        <div style={{
          padding: '20px',
          textAlign: 'center',
          background: 'var(--panel)',
          borderRadius: '8px'
        }}>
          <div style={{ fontSize: '2rem', marginBottom: '12px' }}>🔮</div>
          <p style={{ color: 'var(--text)', marginBottom: '8px', fontWeight: 600 }}>
            Fetch.ai Market Signals
          </p>
          <p style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>
            Configure Fetch.ai API key in API Setup to access market signals and autonomous agents
          </p>
        </div>
      )}

      {/* Flokx Panel */}
      {activeTab === 'flokx' && (
        <div style={{
          padding: '20px',
          textAlign: 'center',
          background: 'var(--panel)',
          borderRadius: '8px'
        }}>
          <div style={{ fontSize: '2rem', marginBottom: '12px' }}>🧠</div>
          <p style={{ color: 'var(--text)', marginBottom: '8px', fontWeight: 600 }}>
            FlokX AI Alerts
          </p>
          <p style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>
            Configure FlokX API key in API Setup to receive AI-powered trading alerts
          </p>
        </div>
      )}
    </div>
  );
}
