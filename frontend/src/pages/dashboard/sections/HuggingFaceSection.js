import React, { useState, useEffect } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { apiClient } from '@/lib/apiClient';
import { toast } from 'sonner';

/**
 * HuggingFace Section
 * 
 * Provides UI for HuggingFace AI model integration:
 * - Task selection (sentiment analysis, summarization, translation, etc.)
 * - Model selection for the chosen task
 * - Forms to submit text for analysis
 * - Display results with error handling
 */
const HuggingFaceSection = () => {
  const [isConfigured, setIsConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState([]);
  const [models, setModels] = useState([]);
  const [selectedTask, setSelectedTask] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [inputText, setInputText] = useState('');
  const [result, setResult] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [modelLimit, setModelLimit] = useState(10);

  // Check HuggingFace API key configuration
  useEffect(() => {
    checkConfiguration();
    if (isConfigured) {
      fetchTasks();
    }
  }, [isConfigured]);

  // Fetch models when task changes
  useEffect(() => {
    if (selectedTask && isConfigured) {
      fetchModels(selectedTask);
    }
  }, [selectedTask]);

  const checkConfiguration = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get('/huggingface/test-connection');
      setIsConfigured(response.data.configured || false);
      if (!response.data.configured) {
        setError('HuggingFace API key not configured');
      }
    } catch (err) {
      console.error('Failed to check HuggingFace configuration:', err);
      setIsConfigured(false);
      setError(err.response?.data?.detail || 'Failed to connect to HuggingFace API');
    } finally {
      setLoading(false);
    }
  };

  const fetchTasks = async () => {
    try {
      const response = await apiClient.get('/huggingface/tasks');
      setTasks(response.data.tasks || []);
      if (response.data.tasks && response.data.tasks.length > 0) {
        // Set default task to sentiment analysis or first available
        const defaultTask = response.data.tasks.find(t => t === 'text-classification') || response.data.tasks[0];
        setSelectedTask(defaultTask);
      }
    } catch (err) {
      console.error('Failed to fetch HuggingFace tasks:', err);
      toast.error('Failed to load available tasks');
    }
  };

  const fetchModels = async (task) => {
    try {
      setModels([]);
      setSelectedModel('');
      const response = await apiClient.get(`/huggingface/models?task=${task}&limit=${modelLimit}`);
      const modelList = response.data.models || [];
      setModels(modelList);
      
      // Auto-select first model if available
      if (modelList.length > 0) {
        setSelectedModel(modelList[0].modelId || modelList[0].id || '');
      }
    } catch (err) {
      console.error('Failed to fetch models:', err);
      toast.error('Failed to load models for selected task');
    }
  };

  const handleAnalyze = async () => {
    if (!inputText.trim()) {
      toast.error('Please enter text to analyze');
      return;
    }

    setProcessing(true);
    setResult(null);
    setError(null);

    try {
      let response;
      
      // Use appropriate endpoint based on task
      if (selectedTask === 'text-classification' || selectedTask === 'sentiment-analysis') {
        response = await apiClient.post('/huggingface/analyze-sentiment', {
          text: inputText,
          model_id: selectedModel || undefined
        });
      } else if (selectedTask === 'summarization') {
        response = await apiClient.post('/huggingface/summarize', {
          text: inputText,
          model_id: selectedModel || undefined
        });
      } else {
        toast.error('Task not yet supported in UI. Please use sentiment analysis or summarization.');
        setProcessing(false);
        return;
      }

      setResult(response.data);
      toast.success('Analysis complete!');
    } catch (err) {
      console.error('Analysis failed:', err);
      const errorMsg = err.response?.data?.detail || err.message || 'Analysis failed';
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setProcessing(false);
    }
  };

  const handleClear = () => {
    setInputText('');
    setResult(null);
    setError(null);
  };

  if (loading) {
    return (
      <section className="section active">
        <div className="card">
          <SectionHeader
            title="🤗 HuggingFace AI"
            subtitle="Access powerful AI models for text analysis, summarization, and more"
          />
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--muted)' }}>
            Loading HuggingFace integration...
          </div>
        </div>
      </section>
    );
  }

  if (!isConfigured) {
    return (
      <section className="section active">
        <div className="card">
          <SectionHeader
            title="🤗 HuggingFace AI"
            subtitle="Access powerful AI models for text analysis, summarization, and more"
          />
          <div style={{
            padding: '40px',
            textAlign: 'center',
            background: 'var(--panel)',
            borderRadius: '8px',
            border: '1px solid var(--line)',
            marginBottom: '20px'
          }}>
            <div style={{ fontSize: '3rem', marginBottom: '16px' }}>🤗</div>
            <h3 style={{ marginBottom: '12px', color: 'var(--text)' }}>
              HuggingFace Not Configured
            </h3>
            <p style={{
              color: 'var(--muted)',
              marginBottom: '20px',
              maxWidth: '600px',
              margin: '0 auto 20px'
            }}>
              Connect your HuggingFace API key to access thousands of pre-trained AI models for
              sentiment analysis, text summarization, translation, question answering, and more.
            </p>
            {error && (
              <div style={{
                padding: '12px',
                marginBottom: '20px',
                background: 'var(--error-bg)',
                color: 'var(--error)',
                borderRadius: '6px',
                fontSize: '0.9rem',
                maxWidth: '600px',
                margin: '0 auto 20px'
              }}>
                {error}
              </div>
            )}
            <button
              onClick={() => window.location.hash = '#/dashboard?section=api'}
              style={{
                padding: '12px 24px',
                background: 'var(--accent2)',
                color: 'var(--text)',
                border: 'none',
                borderRadius: '8px',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: '1rem'
              }}
            >
              Configure HuggingFace API
            </button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🤗 HuggingFace AI"
          subtitle="Access powerful AI models for text analysis, summarization, and more"
        />

        {/* Task Selection */}
        <div style={{ marginBottom: '20px' }}>
          <label style={{
            display: 'block',
            marginBottom: '8px',
            fontWeight: 600,
            color: 'var(--text)'
          }}>
            Select Task
          </label>
          <select
            value={selectedTask}
            onChange={(e) => setSelectedTask(e.target.value)}
            style={{
              width: '100%',
              padding: '12px',
              background: 'var(--panel)',
              border: '1px solid var(--line)',
              borderRadius: '8px',
              color: 'var(--text)',
              fontSize: '1rem',
              cursor: 'pointer'
            }}
          >
            <option value="">-- Select a task --</option>
            {tasks.map(task => (
              <option key={task} value={task}>
                {task.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
              </option>
            ))}
          </select>
        </div>

        {/* Model Selection */}
        {models.length > 0 && (
          <div style={{ marginBottom: '20px' }}>
            <label style={{
              display: 'block',
              marginBottom: '8px',
              fontWeight: 600,
              color: 'var(--text)'
            }}>
              Select Model (optional)
            </label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              style={{
                width: '100%',
                padding: '12px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '8px',
                color: 'var(--text)',
                fontSize: '1rem',
                cursor: 'pointer'
              }}
            >
              <option value="">-- Default model --</option>
              {models.map(model => (
                <option key={model.modelId || model.id} value={model.modelId || model.id}>
                  {model.modelId || model.id}
                </option>
              ))}
            </select>
            <div style={{
              fontSize: '0.85rem',
              color: 'var(--muted)',
              marginTop: '4px'
            }}>
              Showing {models.length} models. Increase limit to see more.
            </div>
          </div>
        )}

        {/* Input Text Area */}
        <div style={{ marginBottom: '20px' }}>
          <label style={{
            display: 'block',
            marginBottom: '8px',
            fontWeight: 600,
            color: 'var(--text)'
          }}>
            Enter Text to Analyze
          </label>
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={
              selectedTask === 'summarization'
                ? 'Enter a long text to summarize...'
                : 'Enter text for sentiment analysis...'
            }
            style={{
              width: '100%',
              minHeight: '150px',
              padding: '12px',
              background: 'var(--panel)',
              border: '1px solid var(--line)',
              borderRadius: '8px',
              color: 'var(--text)',
              fontSize: '1rem',
              fontFamily: 'inherit',
              resize: 'vertical'
            }}
          />
        </div>

        {/* Action Buttons */}
        <div style={{
          display: 'flex',
          gap: '12px',
          marginBottom: '20px'
        }}>
          <button
            onClick={handleAnalyze}
            disabled={processing || !inputText.trim()}
            style={{
              padding: '12px 24px',
              background: processing ? 'var(--muted)' : 'var(--success)',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontWeight: 600,
              cursor: processing ? 'not-allowed' : 'pointer',
              fontSize: '1rem',
              flex: 1
            }}
          >
            {processing ? '🔄 Processing...' : '✨ Analyze'}
          </button>
          <button
            onClick={handleClear}
            disabled={processing}
            style={{
              padding: '12px 24px',
              background: 'var(--panel)',
              color: 'var(--text)',
              border: '1px solid var(--line)',
              borderRadius: '8px',
              fontWeight: 600,
              cursor: processing ? 'not-allowed' : 'pointer',
              fontSize: '1rem'
            }}
          >
            Clear
          </button>
        </div>

        {/* Results */}
        {result && (
          <div style={{
            padding: '20px',
            background: 'var(--glass)',
            border: '2px solid var(--success)',
            borderRadius: '8px',
            marginBottom: '20px'
          }}>
            <h3 style={{
              marginBottom: '16px',
              color: 'var(--text)',
              fontSize: '1.1rem'
            }}>
              📊 Results
            </h3>
            
            {/* Sentiment Analysis Results */}
            {result.label && (
              <div style={{ marginBottom: '12px' }}>
                <div style={{
                  fontSize: '0.9rem',
                  color: 'var(--muted)',
                  marginBottom: '4px'
                }}>
                  Sentiment
                </div>
                <div style={{
                  fontSize: '1.2rem',
                  fontWeight: 600,
                  color: result.label === 'POSITIVE' ? 'var(--success)' : 
                        result.label === 'NEGATIVE' ? 'var(--error)' : 
                        'var(--warning)'
                }}>
                  {result.label}
                  {result.score && ` (${(result.score * 100).toFixed(1)}% confidence)`}
                </div>
              </div>
            )}

            {/* Summarization Results */}
            {result.summary_text && (
              <div style={{ marginBottom: '12px' }}>
                <div style={{
                  fontSize: '0.9rem',
                  color: 'var(--muted)',
                  marginBottom: '4px'
                }}>
                  Summary
                </div>
                <div style={{
                  padding: '12px',
                  background: 'var(--panel)',
                  borderRadius: '6px',
                  color: 'var(--text)',
                  lineHeight: '1.6'
                }}>
                  {result.summary_text}
                </div>
              </div>
            )}

            {/* Model Info */}
            {result.model_used && (
              <div style={{
                fontSize: '0.85rem',
                color: 'var(--muted)',
                marginTop: '12px'
              }}>
                Model: {result.model_used}
              </div>
            )}
          </div>
        )}

        {/* Error Display */}
        {error && !result && (
          <div style={{
            padding: '16px',
            background: 'var(--error-bg)',
            border: '1px solid var(--error)',
            borderRadius: '8px',
            color: 'var(--error)',
            marginBottom: '20px'
          }}>
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Help Text */}
        <div style={{
          padding: '12px',
          background: 'var(--glass)',
          border: '1px solid var(--line)',
          borderRadius: '8px',
          fontSize: '0.85rem',
          color: 'var(--muted)'
        }}>
          <strong>💡 Supported Tasks:</strong> Currently supports sentiment analysis and text summarization.
          More tasks (translation, question answering, etc.) coming soon!
        </div>
      </div>
    </section>
  );
};

export default HuggingFaceSection;
