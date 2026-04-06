import React, { useState, useEffect } from 'react';
import { apiClient } from '@/lib/apiClient';
import { toast } from 'sonner';

/**
 * Learning Results Modal
 * Shows learning analysis and allows applying recommended adjustments to bots
 */
export default function LearningResultsModal({ botId, botName, onClose, onApplied }) {
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (botId) {
      fetchLearningAnalysis();
    }
  }, [botId]);

  const fetchLearningAnalysis = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.get(`/phase6/learning/analyze/${botId}`);
      setAnalysis(response.data);
    } catch (err) {
      console.error('Failed to fetch learning analysis:', err);
      setError(err.response?.data?.detail || 'Failed to load learning analysis');
    } finally {
      setLoading(false);
    }
  };

  const handleApplyAdjustments = async () => {
    try {
      setApplying(true);
      await apiClient.post(`/phase6/learning/apply-adjustments/${botId}`);
      toast.success('Adjustments applied successfully!');
      if (onApplied) {
        onApplied();
      }
      onClose();
    } catch (err) {
      console.error('Failed to apply adjustments:', err);
      toast.error(err.response?.data?.detail || 'Failed to apply adjustments');
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div 
        className="modal-content" 
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '600px', maxHeight: '80vh', overflow: 'auto' }}
      >
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '20px'
        }}>
          <h3 style={{ margin: 0, color: 'var(--text)' }}>
            📚 Learning Report: {botName}
          </h3>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              fontSize: '1.5rem',
              cursor: 'pointer',
              color: 'var(--text)',
              padding: '4px 8px'
            }}
          >
            ×
          </button>
        </div>

        {loading && (
          <div style={{
            padding: '40px',
            textAlign: 'center',
            color: 'var(--muted)'
          }}>
            Loading learning analysis...
          </div>
        )}

        {error && (
          <div style={{
            padding: '20px',
            background: 'var(--error-bg)',
            border: '1px solid var(--error)',
            borderRadius: '8px',
            color: 'var(--error)',
            marginBottom: '20px'
          }}>
            <strong>Error:</strong> {error}
          </div>
        )}

        {!loading && !error && analysis && (
          <div>
            {/* Metrics Summary */}
            <div style={{
              padding: '16px',
              background: 'var(--panel)',
              border: '1px solid var(--line)',
              borderRadius: '8px',
              marginBottom: '20px'
            }}>
              <div style={{
                fontSize: '0.9rem',
                fontWeight: 600,
                color: 'var(--text)',
                marginBottom: '12px'
              }}>
                Performance Metrics
              </div>
              
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: '12px'
              }}>
                {analysis.metrics?.win_rate !== undefined && (
                  <div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Win Rate</div>
                    <div style={{
                      fontSize: '1.1rem',
                      fontWeight: 600,
                      color: analysis.metrics.win_rate >= 50 ? 'var(--success)' : 'var(--warning)'
                    }}>
                      {analysis.metrics.win_rate.toFixed(1)}%
                    </div>
                  </div>
                )}
                
                {analysis.metrics?.total_profit !== undefined && (
                  <div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Total Profit</div>
                    <div style={{
                      fontSize: '1.1rem',
                      fontWeight: 600,
                      color: analysis.metrics.total_profit >= 0 ? 'var(--success)' : 'var(--error)'
                    }}>
                      R {analysis.metrics.total_profit.toFixed(2)}
                    </div>
                  </div>
                )}
                
                {analysis.metrics?.total_fees !== undefined && (
                  <div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Total Fees</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text)' }}>
                      R {Math.abs(analysis.metrics.total_fees).toFixed(2)}
                    </div>
                  </div>
                )}
                
                {analysis.metrics?.max_drawdown !== undefined && (
                  <div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Max Drawdown</div>
                    <div style={{
                      fontSize: '1.1rem',
                      fontWeight: 600,
                      color: 'var(--error)'
                    }}>
                      {analysis.metrics.max_drawdown.toFixed(1)}%
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Recommended Adjustments */}
            {analysis.recommendations && analysis.recommendations.length > 0 && (
              <div style={{
                padding: '16px',
                background: 'var(--glass)',
                border: '2px solid var(--accent)',
                borderRadius: '8px',
                marginBottom: '20px'
              }}>
                <div style={{
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  color: 'var(--text)',
                  marginBottom: '12px'
                }}>
                  💡 Recommended Adjustments
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {analysis.recommendations.map((rec, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '12px',
                        background: 'var(--panel)',
                        borderRadius: '6px',
                        border: '1px solid var(--line)'
                      }}
                    >
                      <div style={{
                        fontSize: '0.85rem',
                        fontWeight: 600,
                        color: 'var(--text)',
                        marginBottom: '4px'
                      }}>
                        {rec.parameter || rec.field}
                      </div>
                      <div style={{
                        fontSize: '0.8rem',
                        color: 'var(--muted)',
                        marginBottom: '4px'
                      }}>
                        Current: <span style={{ color: 'var(--text)' }}>{rec.current_value}</span>
                        {' → '}
                        Suggested: <span style={{ color: 'var(--accent)' }}>{rec.suggested_value}</span>
                      </div>
                      {rec.reason && (
                        <div style={{
                          fontSize: '0.75rem',
                          color: 'var(--muted)',
                          marginTop: '4px',
                          fontStyle: 'italic'
                        }}>
                          {rec.reason}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Analysis Summary */}
            {analysis.summary && (
              <div style={{
                padding: '12px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '8px',
                marginBottom: '20px'
              }}>
                <div style={{
                  fontSize: '0.85rem',
                  color: 'var(--text)',
                  lineHeight: '1.6'
                }}>
                  {analysis.summary}
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
              {analysis.recommendations && analysis.recommendations.length > 0 && (
                <button
                  onClick={handleApplyAdjustments}
                  disabled={applying}
                  style={{
                    flex: 1,
                    padding: '12px 24px',
                    background: applying ? 'var(--muted)' : 'var(--success)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '8px',
                    fontWeight: 600,
                    cursor: applying ? 'not-allowed' : 'pointer',
                    fontSize: '1rem'
                  }}
                >
                  {applying ? '⏳ Applying...' : '✅ Apply Adjustments'}
                </button>
              )}
              <button
                onClick={onClose}
                style={{
                  padding: '12px 24px',
                  background: 'var(--panel)',
                  color: 'var(--text)',
                  border: '1px solid var(--line)',
                  borderRadius: '8px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontSize: '1rem'
                }}
              >
                Close
              </button>
            </div>

            {/* Help Text */}
            <div style={{
              marginTop: '16px',
              padding: '12px',
              background: 'var(--glass)',
              border: '1px solid var(--line)',
              borderRadius: '8px',
              fontSize: '0.8rem',
              color: 'var(--muted)'
            }}>
              <strong>💡 Note:</strong> Adjustments are based on historical performance and may take time to show results.
              The learning system analyzes trades from the last 7 days.
            </div>
          </div>
        )}

        {!loading && !error && !analysis && (
          <div style={{
            padding: '40px',
            textAlign: 'center',
            color: 'var(--muted)'
          }}>
            No learning data available yet. The bot needs at least 7 days of trading history.
          </div>
        )}
      </div>
    </div>
  );
}
