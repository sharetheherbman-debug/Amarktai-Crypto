import React, { useState } from 'react';
import { Play, Pause, Square, RotateCw, AlertCircle } from 'lucide-react';
import { post, notifyError } from '../lib/apiClient';

/**
 * Bot Lifecycle Controls Component
 * Provides buttons for start, pause, stop, and resume bot operations
 */
const BotLifecycleControls = ({ bot, onAction, compact = false }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleAction = async (action) => {
    setLoading(true);
    setError(null);

    try {
      const data = await post(`/bots/${bot.id}/${action}`, {
        reason: `Manual ${action} by user`
      });

      if (data?.success) {
        if (onAction) {
          onAction(action, data);
        }
      } else {
        const detailMessage = data?.detail?.message || data?.detail?.message || data?.detail;
        setError(data.message || detailMessage || `Failed to ${action} bot`);
      }
    } catch (err) {
      setError(`Error: ${err.message}`);
      notifyError(err);
    } finally {
      setLoading(false);
    }
  };

  const status = bot?.status || 'unknown';

  // Compact view - minimal buttons
  if (compact) {
    return (
      <div className="flex gap-1">
        {status === 'active' && (
          <button
            onClick={() => handleAction('pause')}
            disabled={loading}
            className="p-1 text-yellow-600 hover:bg-yellow-50 rounded transition disabled:opacity-50"
            title="Pause bot"
          >
            <Pause size={16} />
          </button>
        )}
        {status === 'paused' && (
          <button
            onClick={() => handleAction('resume')}
            disabled={loading}
            className="p-1 text-green-600 hover:bg-green-50 rounded transition disabled:opacity-50"
            title="Resume bot"
          >
            <RotateCw size={16} />
          </button>
        )}
        {status === 'stopped' && (
          <button
            onClick={() => handleAction('start')}
            disabled={loading}
            className="p-1 text-blue-600 hover:bg-blue-50 rounded transition disabled:opacity-50"
            title="Start bot"
          >
            <Play size={16} />
          </button>
        )}
        {error && (
          <span className="text-xs text-red-500" title={error}>
            <AlertCircle size={14} />
          </span>
        )}
      </div>
    );
  }

  // Full view - all buttons with labels
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {/* Start button - only show if stopped */}
        {status === 'stopped' && (
          <button
            onClick={() => handleAction('start')}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play size={16} />
            <span>Start</span>
          </button>
        )}

        {/* Pause button - only show if active */}
        {status === 'active' && (
          <button
            onClick={() => handleAction('pause')}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Pause size={16} />
            <span>Pause</span>
          </button>
        )}

        {/* Resume button - only show if paused */}
        {status === 'paused' && (
          <button
            onClick={() => handleAction('resume')}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RotateCw size={16} />
            <span>Resume</span>
          </button>
        )}

        {/* Stop button - show if active or paused */}
        {(status === 'active' || status === 'paused') && (
          <button
            onClick={() => {
              if (window.confirm('Are you sure you want to stop this bot? This action will require restarting the bot.')) {
                handleAction('stop');
              }
            }}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Square size={16} />
            <span>Stop</span>
          </button>
        )}
      </div>

      {/* Loading state */}
      {loading && (
        <div className="text-sm text-gray-500 animate-pulse">
          Processing...
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 p-2 rounded">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Status badge */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-600">Status:</span>
        <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
          status === 'active' ? 'bg-green-100 text-green-800' :
          status === 'paused' ? 'bg-yellow-100 text-yellow-800' :
          status === 'stopped' ? 'bg-red-100 text-red-800' :
          'bg-gray-100 text-gray-800'
        }`}>
          {status.toUpperCase()}
        </span>
      </div>
    </div>
  );
};

export default BotLifecycleControls;
