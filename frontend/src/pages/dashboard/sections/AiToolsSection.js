import React, { useState, useEffect } from 'react';
import { apiClient } from '@/lib/apiClient';
import { toast } from 'sonner';
import LearningResultsModal from './LearningResultsModal';

/**
 * AI Tools Hub - Unified AI tools interface
 * Consolidates Learning, Sentiment Analysis, Strategy Insights, and Agent Creation
 * Replaces standalone Fetch.ai/Flokx/HuggingFace panels per requirements
 */
export default function AiToolsSection({ bots, onRefresh }) {
  const [activeTab, setActiveTab] = useState('learning');
  
  // Learning & RL state
  const [selectedBotForLearning, setSelectedBotForLearning] = useState(null);
  const [learningModalOpen, setLearningModalOpen] = useState(false);
  const [rlMetrics, setRlMetrics] = useState(null);
  const [rlLoading, setRlLoading] = useState(false);
  
  // Sentiment & Summarization state (HuggingFace)
  const [hfConfigured, setHfConfigured] = useState(false);
  const [hfTasks, setHfTasks] = useState([]);
  const [hfSelectedTask, setHfSelectedTask] = useState('text-classification');
  const [hfInputText, setHfInputText] = useState('');
  const [hfResult, setHfResult] = useState(null);
  const [hfProcessing, setHfProcessing] = useState(false);
  
  // Classification state
  const [classificationLabels, setClassificationLabels] = useState('bullish,bearish,neutral');
  const [classificationResult, setClassificationResult] = useState(null);
  
  // Embeddings state
  const [embeddingsText, setEmbeddingsText] = useState('');
  const [embeddingsResult, setEmbeddingsResult] = useState(null);
  
  // Agent Creation state
  const [agentType, setAgentType] = useState('fetchai');
  const [agentName, setAgentName] = useState('');
  const [agentStrategy, setAgentStrategy] = useState('adaptive');
  const [agentCapital, setAgentCapital] = useState('1000');
  const [agentRiskTier, setAgentRiskTier] = useState('balanced');
  const [agents, setAgents] = useState([]);
  const [agentCreating, setAgentCreating] = useState(false);

  // Load initial data
  useEffect(() => {
    checkHuggingFaceConfig();
    fetchRLMetrics();
    fetchAgents();
  }, []);

  useEffect(() => {
    if (hfConfigured) {
      fetchHuggingFaceTasks();
    }
  }, [hfConfigured]);

  // HuggingFace Configuration Check
  const checkHuggingFaceConfig = async () => {
    try {
      const response = await apiClient.get('/huggingface/test-connection');
      setHfConfigured(response.data.configured || false);
    } catch (err) {
      console.error('HuggingFace config check failed:', err);
      setHfConfigured(false);
    }
  };

  const fetchHuggingFaceTasks = async () => {
    try {
      const response = await apiClient.get('/huggingface/tasks');
      setHfTasks(response.data.tasks || []);
    } catch (err) {
      console.error('Failed to fetch HuggingFace tasks:', err);
    }
  };

  // RL Metrics Fetching
  const fetchRLMetrics = async () => {
    try {
      setRlLoading(true);
      const response = await apiClient.get('/ai/rl-status');
      setRlMetrics(response.data);
    } catch (err) {
      console.error('Failed to fetch RL metrics:', err);
      // Gracefully handle if endpoint doesn't exist yet
      setRlMetrics(null);
    } finally {
      setRlLoading(false);
    }
  };

  // Agent Management
  const fetchAgents = async () => {
    try {
      const response = await apiClient.get('/agents/status');
      setAgents(response.data.agents || []);
    } catch (err) {
      console.error('Failed to fetch agents:', err);
      setAgents([]);
    }
  };

  const handleCreateAgent = async (e) => {
    e.preventDefault();
    
    if (!agentName.trim()) {
      toast.error('Please enter an agent name');
      return;
    }

    try {
      setAgentCreating(true);
      await apiClient.post('/agents/create', {
        name: agentName,
        type: agentType,
        strategy: agentStrategy,
        capital: parseFloat(agentCapital),
        risk_tier: agentRiskTier
      });
      
      toast.success(`${agentType === 'fetchai' ? 'Fetch.ai' : 'FlokX'} agent created successfully!`);
      setAgentName('');
      setAgentCapital('1000');
      fetchAgents();
    } catch (err) {
      console.error('Failed to create agent:', err);
      toast.error(err.response?.data?.detail || 'Failed to create agent');
    } finally {
      setAgentCreating(false);
    }
  };

  // HuggingFace Actions
  const handleSentimentAnalysis = async () => {
    if (!hfInputText.trim()) {
      toast.error('Please enter text to analyze');
      return;
    }

    try {
      setHfProcessing(true);
      const response = await apiClient.post('/huggingface/analyze-sentiment', {
        text: hfInputText
      });
      setHfResult(response.data);
      toast.success('Analysis complete!');
    } catch (err) {
      console.error('Sentiment analysis failed:', err);
      toast.error(err.response?.data?.detail || 'Analysis failed');
    } finally {
      setHfProcessing(false);
    }
  };

  const handleSummarization = async () => {
    if (!hfInputText.trim()) {
      toast.error('Please enter text to summarize');
      return;
    }

    try {
      setHfProcessing(true);
      const response = await apiClient.post('/huggingface/summarize', {
        text: hfInputText
      });
      setHfResult(response.data);
      toast.success('Summarization complete!');
    } catch (err) {
      console.error('Summarization failed:', err);
      toast.error(err.response?.data?.detail || 'Summarization failed');
    } finally {
      setHfProcessing(false);
    }
  };

  const handleClassification = async () => {
    if (!hfInputText.trim()) {
      toast.error('Please enter text to classify');
      return;
    }

    try {
      setHfProcessing(true);
      const response = await apiClient.post('/huggingface/classify', {
        text: hfInputText,
        labels: classificationLabels.split(',').map(l => l.trim())
      });
      setClassificationResult(response.data);
      toast.success('Classification complete!');
    } catch (err) {
      console.error('Classification failed:', err);
      toast.error(err.response?.data?.detail || 'Classification failed');
    } finally {
      setHfProcessing(false);
    }
  };

  const handleEmbeddings = async () => {
    if (!embeddingsText.trim()) {
      toast.error('Please enter text for embeddings');
      return;
    }

    try {
      setHfProcessing(true);
      const response = await apiClient.post('/huggingface/embeddings', {
        text: embeddingsText
      });
      setEmbeddingsResult(response.data);
      toast.success('Embeddings generated!');
    } catch (err) {
      console.error('Embeddings failed:', err);
      toast.error(err.response?.data?.detail || 'Embeddings generation failed');
    } finally {
      setHfProcessing(false);
    }
  };

  const openLearningModal = (bot) => {
    setSelectedBotForLearning(bot);
    setLearningModalOpen(true);
  };

  const closeLearningModal = () => {
    setLearningModalOpen(false);
    setSelectedBotForLearning(null);
  };

  return (
    <section className="section active">
      <div className="card">
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '20px'
        }}>
          <div>
            <h2 style={{ margin: 0, color: 'var(--text)', fontSize: '1.5rem' }}>
              🧠 AI Tools Hub
            </h2>
            <p style={{ margin: '8px 0 0 0', color: 'var(--muted)', fontSize: '0.9rem' }}>
              Unified AI tools for learning, analysis, and agent management
            </p>
          </div>
        </div>

        {/* Tab Navigation */}
        <div style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '24px',
          flexWrap: 'wrap',
          borderBottom: '1px solid var(--line)',
          paddingBottom: '8px'
        }}>
          <button
            onClick={() => setActiveTab('learning')}
            style={{
              padding: '10px 20px',
              background: activeTab === 'learning' ? 'var(--accent)' : 'transparent',
              color: activeTab === 'learning' ? 'white' : 'var(--text)',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.95rem',
              transition: 'all 0.2s'
            }}
          >
            📚 Learning & RL
          </button>
          <button
            onClick={() => setActiveTab('sentiment')}
            style={{
              padding: '10px 20px',
              background: activeTab === 'sentiment' ? 'var(--accent)' : 'transparent',
              color: activeTab === 'sentiment' ? 'white' : 'var(--text)',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.95rem',
              transition: 'all 0.2s'
            }}
          >
            💬 Sentiment & Summarization
          </button>
          <button
            onClick={() => setActiveTab('classification')}
            style={{
              padding: '10px 20px',
              background: activeTab === 'classification' ? 'var(--accent)' : 'transparent',
              color: activeTab === 'classification' ? 'white' : 'var(--text)',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.95rem',
              transition: 'all 0.2s'
            }}
          >
            🎯 Classification & Embeddings
          </button>
          <button
            onClick={() => setActiveTab('agents')}
            style={{
              padding: '10px 20px',
              background: activeTab === 'agents' ? 'var(--accent)' : 'transparent',
              color: activeTab === 'agents' ? 'white' : 'var(--text)',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.95rem',
              transition: 'all 0.2s'
            }}
          >
            🤖 Agent Creation
          </button>
        </div>

        {/* Tab Content */}
        <div style={{ minHeight: '400px' }}>
          {/* Learning & RL Metrics Tab */}
          {activeTab === 'learning' && (
            <div>
              <h3 style={{ marginBottom: '16px', color: 'var(--text)' }}>
                Learning Results & RL Metrics
              </h3>
              
              {/* RL Metrics Display */}
              {rlMetrics && (
                <div style={{
                  padding: '16px',
                  background: 'var(--glass)',
                  border: '1px solid var(--line)',
                  borderRadius: '8px',
                  marginBottom: '20px'
                }}>
                  <h4 style={{ marginBottom: '12px', color: 'var(--text)' }}>
                    Reinforcement Learning Status
                  </h4>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                    gap: '12px'
                  }}>
                    <div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Episodes</div>
                      <div style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--text)' }}>
                        {rlMetrics.episodes || 0}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Avg Reward</div>
                      <div style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--success)' }}>
                        {rlMetrics.avg_reward?.toFixed(2) || '0.00'}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Policy Updates</div>
                      <div style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--text)' }}>
                        {rlMetrics.policy_updates || 0}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Bot Learning Analysis */}
              <div style={{
                padding: '16px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '8px'
              }}>
                <h4 style={{ marginBottom: '12px', color: 'var(--text)' }}>
                  Bot Learning Analysis
                </h4>
                <p style={{ fontSize: '0.9rem', color: 'var(--muted)', marginBottom: '16px' }}>
                  Select a bot to view learning recommendations and performance metrics
                </p>
                
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
                  gap: '12px'
                }}>
                  {bots && bots.length > 0 ? (
                    bots.map(bot => (
                      <div
                        key={bot.id}
                        style={{
                          padding: '12px',
                          background: 'var(--glass)',
                          border: '1px solid var(--line)',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          transition: 'all 0.2s'
                        }}
                        onClick={() => openLearningModal(bot)}
                      >
                        <div style={{
                          fontWeight: 600,
                          color: 'var(--text)',
                          marginBottom: '8px'
                        }}>
                          {bot.name || `Bot ${bot.id}`}
                        </div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                          {bot.exchange?.toUpperCase()} • {bot.pair}
                        </div>
                        <div style={{
                          marginTop: '8px',
                          fontSize: '0.8rem',
                          color: bot.status === 'active' ? 'var(--success)' : 'var(--warning)'
                        }}>
                          {bot.status}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div style={{ color: 'var(--muted)', padding: '20px', textAlign: 'center' }}>
                      No bots available. Create a bot to see learning analysis.
                    </div>
                  )}
                </div>
              </div>

              <button
                onClick={fetchRLMetrics}
                disabled={rlLoading}
                style={{
                  marginTop: '16px',
                  padding: '10px 20px',
                  background: 'var(--accent)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: rlLoading ? 'not-allowed' : 'pointer',
                  fontWeight: 600
                }}
              >
                {rlLoading ? '⏳ Loading...' : '🔄 Refresh Metrics'}
              </button>
            </div>
          )}

          {/* Sentiment & Summarization Tab */}
          {activeTab === 'sentiment' && (
            <div>
              <h3 style={{ marginBottom: '16px', color: 'var(--text)' }}>
                Sentiment Analysis & Text Summarization
              </h3>
              
              {!hfConfigured ? (
                <div style={{
                  padding: '40px',
                  textAlign: 'center',
                  background: 'var(--panel)',
                  borderRadius: '8px'
                }}>
                  <div style={{ fontSize: '3rem', marginBottom: '16px' }}>🤗</div>
                  <p style={{ color: 'var(--muted)', marginBottom: '16px' }}>
                    HuggingFace API key not configured
                  </p>
                  <button
                    onClick={() => window.location.hash = '#/dashboard?section=api'}
                    style={{
                      padding: '10px 20px',
                      background: 'var(--accent)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: 600
                    }}
                  >
                    Configure API Key
                  </button>
                </div>
              ) : (
                <div>
                  <div style={{ marginBottom: '16px' }}>
                    <label style={{
                      display: 'block',
                      marginBottom: '8px',
                      fontWeight: 600,
                      color: 'var(--text)'
                    }}>
                      Input Text
                    </label>
                    <textarea
                      value={hfInputText}
                      onChange={(e) => setHfInputText(e.target.value)}
                      placeholder="Enter text for analysis or summarization..."
                      style={{
                        width: '100%',
                        minHeight: '150px',
                        padding: '12px',
                        background: 'var(--panel)',
                        border: '1px solid var(--line)',
                        borderRadius: '8px',
                        color: 'var(--text)',
                        fontSize: '0.95rem',
                        fontFamily: 'inherit',
                        resize: 'vertical'
                      }}
                    />
                  </div>

                  <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
                    <button
                      onClick={handleSentimentAnalysis}
                      disabled={hfProcessing}
                      style={{
                        padding: '10px 20px',
                        background: hfProcessing ? 'var(--muted)' : 'var(--success)',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: hfProcessing ? 'not-allowed' : 'pointer',
                        fontWeight: 600,
                        flex: 1
                      }}
                    >
                      {hfProcessing ? '⏳ Processing...' : '😊 Analyze Sentiment'}
                    </button>
                    <button
                      onClick={handleSummarization}
                      disabled={hfProcessing}
                      style={{
                        padding: '10px 20px',
                        background: hfProcessing ? 'var(--muted)' : 'var(--accent2)',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: hfProcessing ? 'not-allowed' : 'pointer',
                        fontWeight: 600,
                        flex: 1
                      }}
                    >
                      {hfProcessing ? '⏳ Processing...' : '📝 Summarize'}
                    </button>
                  </div>

                  {/* Results */}
                  {hfResult && (
                    <div style={{
                      padding: '16px',
                      background: 'var(--glass)',
                      border: '2px solid var(--success)',
                      borderRadius: '8px'
                    }}>
                      <h4 style={{ marginBottom: '12px', color: 'var(--text)' }}>Results</h4>
                      
                      {hfResult.label && (
                        <div style={{ marginBottom: '12px' }}>
                          <div style={{ fontSize: '0.9rem', color: 'var(--muted)' }}>Sentiment</div>
                          <div style={{
                            fontSize: '1.2rem',
                            fontWeight: 600,
                            color: hfResult.label === 'POSITIVE' ? 'var(--success)' : 
                                  hfResult.label === 'NEGATIVE' ? 'var(--error)' : 
                                  'var(--warning)'
                          }}>
                            {hfResult.label}
                            {hfResult.score && ` (${(hfResult.score * 100).toFixed(1)}%)`}
                          </div>
                        </div>
                      )}
                      
                      {hfResult.summary_text && (
                        <div>
                          <div style={{ fontSize: '0.9rem', color: 'var(--muted)', marginBottom: '8px' }}>
                            Summary
                          </div>
                          <div style={{
                            padding: '12px',
                            background: 'var(--panel)',
                            borderRadius: '6px',
                            color: 'var(--text)',
                            lineHeight: '1.6'
                          }}>
                            {hfResult.summary_text}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Classification & Embeddings Tab */}
          {activeTab === 'classification' && (
            <div>
              <h3 style={{ marginBottom: '16px', color: 'var(--text)' }}>
                Zero-Shot Classification & Embeddings
              </h3>
              
              {!hfConfigured ? (
                <div style={{
                  padding: '40px',
                  textAlign: 'center',
                  background: 'var(--panel)',
                  borderRadius: '8px'
                }}>
                  <div style={{ fontSize: '3rem', marginBottom: '16px' }}>🤗</div>
                  <p style={{ color: 'var(--muted)', marginBottom: '16px' }}>
                    HuggingFace API key not configured
                  </p>
                  <button
                    onClick={() => window.location.hash = '#/dashboard?section=api'}
                    style={{
                      padding: '10px 20px',
                      background: 'var(--accent)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: 600
                    }}
                  >
                    Configure API Key
                  </button>
                </div>
              ) : (
                <div>
                  {/* Classification Section */}
                  <div style={{
                    padding: '16px',
                    background: 'var(--panel)',
                    border: '1px solid var(--line)',
                    borderRadius: '8px',
                    marginBottom: '20px'
                  }}>
                    <h4 style={{ marginBottom: '12px', color: 'var(--text)' }}>
                      Zero-Shot Classification
                    </h4>
                    <p style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '16px' }}>
                      Classify text into custom categories without training
                    </p>
                    
                    <div style={{ marginBottom: '12px' }}>
                      <label style={{
                        display: 'block',
                        marginBottom: '8px',
                        fontWeight: 600,
                        color: 'var(--text)',
                        fontSize: '0.9rem'
                      }}>
                        Classification Labels (comma-separated)
                      </label>
                      <input
                        type="text"
                        value={classificationLabels}
                        onChange={(e) => setClassificationLabels(e.target.value)}
                        placeholder="e.g., bullish, bearish, neutral"
                        style={{
                          width: '100%',
                          padding: '10px',
                          background: 'var(--glass)',
                          border: '1px solid var(--line)',
                          borderRadius: '6px',
                          color: 'var(--text)',
                          fontSize: '0.9rem'
                        }}
                      />
                    </div>

                    <div style={{ marginBottom: '12px' }}>
                      <label style={{
                        display: 'block',
                        marginBottom: '8px',
                        fontWeight: 600,
                        color: 'var(--text)',
                        fontSize: '0.9rem'
                      }}>
                        Text to Classify
                      </label>
                      <textarea
                        value={hfInputText}
                        onChange={(e) => setHfInputText(e.target.value)}
                        placeholder="Enter text to classify..."
                        style={{
                          width: '100%',
                          minHeight: '100px',
                          padding: '10px',
                          background: 'var(--glass)',
                          border: '1px solid var(--line)',
                          borderRadius: '6px',
                          color: 'var(--text)',
                          fontSize: '0.9rem',
                          fontFamily: 'inherit',
                          resize: 'vertical'
                        }}
                      />
                    </div>

                    <button
                      onClick={handleClassification}
                      disabled={hfProcessing}
                      style={{
                        padding: '10px 20px',
                        background: hfProcessing ? 'var(--muted)' : 'var(--accent)',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: hfProcessing ? 'not-allowed' : 'pointer',
                        fontWeight: 600
                      }}
                    >
                      {hfProcessing ? '⏳ Classifying...' : '🎯 Classify'}
                    </button>

                    {classificationResult && (
                      <div style={{
                        marginTop: '16px',
                        padding: '12px',
                        background: 'var(--glass)',
                        border: '1px solid var(--success)',
                        borderRadius: '6px'
                      }}>
                        <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text)', marginBottom: '8px' }}>
                          Classification Results
                        </div>
                        {classificationResult.labels?.map((label, idx) => (
                          <div key={idx} style={{ marginBottom: '8px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                              <span style={{ color: 'var(--text)' }}>{label}</span>
                              <span style={{ color: 'var(--accent)', fontWeight: 600 }}>
                                {(classificationResult.scores[idx] * 100).toFixed(1)}%
                              </span>
                            </div>
                            <div style={{
                              width: '100%',
                              height: '6px',
                              background: 'var(--glass)',
                              borderRadius: '3px',
                              overflow: 'hidden'
                            }}>
                              <div style={{
                                width: `${classificationResult.scores[idx] * 100}%`,
                                height: '100%',
                                background: 'var(--accent)',
                                transition: 'width 0.3s ease'
                              }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Embeddings Section */}
                  <div style={{
                    padding: '16px',
                    background: 'var(--panel)',
                    border: '1px solid var(--line)',
                    borderRadius: '8px'
                  }}>
                    <h4 style={{ marginBottom: '12px', color: 'var(--text)' }}>
                      Text Embeddings
                    </h4>
                    <p style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '16px' }}>
                      Generate semantic embeddings for similarity search and RL features
                    </p>
                    
                    <div style={{ marginBottom: '12px' }}>
                      <textarea
                        value={embeddingsText}
                        onChange={(e) => setEmbeddingsText(e.target.value)}
                        placeholder="Enter text to generate embeddings..."
                        style={{
                          width: '100%',
                          minHeight: '80px',
                          padding: '10px',
                          background: 'var(--glass)',
                          border: '1px solid var(--line)',
                          borderRadius: '6px',
                          color: 'var(--text)',
                          fontSize: '0.9rem',
                          fontFamily: 'inherit',
                          resize: 'vertical'
                        }}
                      />
                    </div>

                    <button
                      onClick={handleEmbeddings}
                      disabled={hfProcessing}
                      style={{
                        padding: '10px 20px',
                        background: hfProcessing ? 'var(--muted)' : 'var(--accent2)',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: hfProcessing ? 'not-allowed' : 'pointer',
                        fontWeight: 600
                      }}
                    >
                      {hfProcessing ? '⏳ Generating...' : '🔢 Generate Embeddings'}
                    </button>

                    {embeddingsResult && (
                      <div style={{
                        marginTop: '16px',
                        padding: '12px',
                        background: 'var(--glass)',
                        border: '1px solid var(--success)',
                        borderRadius: '6px'
                      }}>
                        <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text)', marginBottom: '8px' }}>
                          Embedding Vector
                        </div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '8px' }}>
                          Dimensions: {embeddingsResult.embeddings?.length || 0}
                        </div>
                        <div style={{
                          maxHeight: '150px',
                          overflow: 'auto',
                          padding: '8px',
                          background: 'var(--panel)',
                          borderRadius: '4px',
                          fontSize: '0.8rem',
                          color: 'var(--text)',
                          fontFamily: 'monospace'
                        }}>
                          [{embeddingsResult.embeddings?.slice(0, 10).map(v => v.toFixed(4)).join(', ')}...]
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Agent Creation Tab */}
          {activeTab === 'agents' && (
            <div>
              <h3 style={{ marginBottom: '16px', color: 'var(--text)' }}>
                Agent Creation & Management
              </h3>
              
              <div style={{
                padding: '16px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '8px',
                marginBottom: '20px'
              }}>
                <h4 style={{ marginBottom: '12px', color: 'var(--text)' }}>
                  Create New Agent
                </h4>
                
                <form onSubmit={handleCreateAgent}>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '16px',
                    marginBottom: '16px'
                  }}>
                    <div>
                      <label style={{
                        display: 'block',
                        marginBottom: '8px',
                        fontWeight: 600,
                        color: 'var(--text)',
                        fontSize: '0.9rem'
                      }}>
                        Agent Type
                      </label>
                      <select
                        value={agentType}
                        onChange={(e) => setAgentType(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '10px',
                          background: 'var(--glass)',
                          border: '1px solid var(--line)',
                          borderRadius: '6px',
                          color: 'var(--text)',
                          fontSize: '0.9rem',
                          cursor: 'pointer'
                        }}
                      >
                        <option value="fetchai">🔮 Fetch.ai uAgent</option>
                      </select>
                    </div>

                    <div>
                      <label style={{
                        display: 'block',
                        marginBottom: '8px',
                        fontWeight: 600,
                        color: 'var(--text)',
                        fontSize: '0.9rem'
                      }}>
                        Agent Name
                      </label>
                      <input
                        type="text"
                        value={agentName}
                        onChange={(e) => setAgentName(e.target.value)}
                        placeholder="My Trading Agent"
                        required
                        style={{
                          width: '100%',
                          padding: '10px',
                          background: 'var(--glass)',
                          border: '1px solid var(--line)',
                          borderRadius: '6px',
                          color: 'var(--text)',
                          fontSize: '0.9rem'
                        }}
                      />
                    </div>

                    <div>
                      <label style={{
                        display: 'block',
                        marginBottom: '8px',
                        fontWeight: 600,
                        color: 'var(--text)',
                        fontSize: '0.9rem'
                      }}>
                        Strategy
                      </label>
                      <select
                        value={agentStrategy}
                        onChange={(e) => setAgentStrategy(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '10px',
                          background: 'var(--glass)',
                          border: '1px solid var(--line)',
                          borderRadius: '6px',
                          color: 'var(--text)',
                          fontSize: '0.9rem',
                          cursor: 'pointer'
                        }}
                      >
                        <option value="adaptive">Adaptive</option>
                        <option value="trend">Trend Following</option>
                        <option value="mean_reversion">Mean Reversion</option>
                        <option value="momentum">Momentum</option>
                      </select>
                    </div>

                    <div>
                      <label style={{
                        display: 'block',
                        marginBottom: '8px',
                        fontWeight: 600,
                        color: 'var(--text)',
                        fontSize: '0.9rem'
                      }}>
                        Initial Capital (ZAR)
                      </label>
                      <input
                        type="number"
                        value={agentCapital}
                        onChange={(e) => setAgentCapital(e.target.value)}
                        min="100"
                        step="100"
                        required
                        style={{
                          width: '100%',
                          padding: '10px',
                          background: 'var(--glass)',
                          border: '1px solid var(--line)',
                          borderRadius: '6px',
                          color: 'var(--text)',
                          fontSize: '0.9rem'
                        }}
                      />
                    </div>

                    <div>
                      <label style={{
                        display: 'block',
                        marginBottom: '8px',
                        fontWeight: 600,
                        color: 'var(--text)',
                        fontSize: '0.9rem'
                      }}>
                        Risk Tier
                      </label>
                      <select
                        value={agentRiskTier}
                        onChange={(e) => setAgentRiskTier(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '10px',
                          background: 'var(--glass)',
                          border: '1px solid var(--line)',
                          borderRadius: '6px',
                          color: 'var(--text)',
                          fontSize: '0.9rem',
                          cursor: 'pointer'
                        }}
                      >
                        <option value="safe">Safe (15% limit)</option>
                        <option value="balanced">Balanced (20% limit)</option>
                        <option value="risky">Risky (25% limit)</option>
                      </select>
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={agentCreating}
                    style={{
                      padding: '12px 24px',
                      background: agentCreating ? 'var(--muted)' : 'var(--success)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: agentCreating ? 'not-allowed' : 'pointer',
                      fontWeight: 600,
                      fontSize: '1rem'
                    }}
                  >
                    {agentCreating ? '⏳ Creating...' : '🚀 Create Agent'}
                  </button>
                </form>
              </div>

              {/* Active Agents List */}
              <div style={{
                padding: '16px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '8px'
              }}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '16px'
                }}>
                  <h4 style={{ margin: 0, color: 'var(--text)' }}>
                    Active Agents
                  </h4>
                  <button
                    onClick={fetchAgents}
                    style={{
                      padding: '6px 12px',
                      background: 'var(--glass)',
                      color: 'var(--text)',
                      border: '1px solid var(--line)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontSize: '0.85rem'
                    }}
                  >
                    🔄 Refresh
                  </button>
                </div>

                {agents.length > 0 ? (
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
                    gap: '12px'
                  }}>
                    {agents.map(agent => (
                      <div
                        key={agent.id}
                        style={{
                          padding: '12px',
                          background: 'var(--glass)',
                          border: '1px solid var(--line)',
                          borderRadius: '6px'
                        }}
                      >
                        <div style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginBottom: '8px'
                        }}>
                          <div style={{ fontWeight: 600, color: 'var(--text)' }}>
                            {agent.type === 'fetchai' ? '🔮' : '🧠'} {agent.name}
                          </div>
                          <div style={{
                            padding: '2px 8px',
                            background: agent.status === 'active' ? 'var(--success)' : 'var(--warning)',
                            color: 'white',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 600
                          }}>
                            {agent.status}
                          </div>
                        </div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                          Strategy: {agent.strategy}
                        </div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                          Capital: R {agent.capital?.toFixed(2) || '0.00'}
                        </div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                          Risk: {agent.risk_tier}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{
                    padding: '40px',
                    textAlign: 'center',
                    color: 'var(--muted)'
                  }}>
                    No active agents. Create one above to get started.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Learning Results Modal */}
      {learningModalOpen && selectedBotForLearning && (
        <LearningResultsModal
          botId={selectedBotForLearning.id}
          botName={selectedBotForLearning.name || `Bot ${selectedBotForLearning.id}`}
          onClose={closeLearningModal}
          onApplied={() => {
            closeLearningModal();
            if (onRefresh) onRefresh();
          }}
        />
      )}
    </section>
  );
}
