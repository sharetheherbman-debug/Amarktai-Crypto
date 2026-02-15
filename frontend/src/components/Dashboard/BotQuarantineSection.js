import React, { useState, useEffect } from 'react';
import { get, notifyError } from '../../lib/apiClient';

const BotQuarantineSection = () => {
  const [quarantinedBots, setQuarantinedBots] = useState([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    fetchQuarantineStatus();
    const interval = setInterval(fetchQuarantineStatus, 10000); // Update every 10s
    return () => clearInterval(interval);
  }, []);
  
  const fetchQuarantineStatus = async () => {
    try {
      const data = await get('/quarantine/status');
      setQuarantinedBots(data.quarantined_bots || []);
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch quarantine status:', error);
      notifyError(error);
      setLoading(false);
    }
  };
  
  const formatTimeRemaining = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  };
  
  const getQuarantineColor = (count) => {
    switch(count) {
      case 1: return 'text-yellow-400';
      case 2: return 'text-orange-400';
      case 3: return 'text-red-400';
      default: return 'text-gray-400';
    }
  };
  
  if (loading) {
    return (
      <div className="glass-panel p-6">
        <div className="animate-pulse">Loading quarantine status...</div>
      </div>
    );
  }
  
  if (quarantinedBots.length === 0) {
    return (
      <div className="glass-panel p-6">
        <h3 className="text-xl font-bold mb-4 text-green-400">
          ✅ No Bots in Quarantine
        </h3>
        <p className="text-gray-400">All bots are operating normally.</p>
      </div>
    );
  }
  
  return (
    <div className="glass-panel p-6">
      <h3 className="text-xl font-bold mb-4 text-yellow-400">
        🔒 Bots in Quarantine & Retraining
      </h3>
      
      <div className="space-y-4">
        {quarantinedBots.map((bot) => {
          // Calculate progress safely to avoid division by zero
          const now = Date.now() / 1000;
          const quarantinedAt = new Date(bot.quarantined_at).getTime() / 1000;
          const elapsed = Math.max(0, now - quarantinedAt);
          const totalDuration = elapsed + bot.remaining_seconds;
          const progressPercent = totalDuration > 0 ? (elapsed / totalDuration) * 100 : 0;
          
          return (
            <div key={bot.bot_id} className="bg-black bg-opacity-30 p-4 rounded-lg">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <h4 className="font-semibold text-white">{bot.bot_name}</h4>
                  <p className="text-sm text-gray-400">
                    Quarantine Attempt #{bot.quarantine_count}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Reason: {bot.quarantine_reason}
                  </p>
                </div>
                
                <div className="text-right">
                  <div className={`text-2xl font-bold ${getQuarantineColor(bot.quarantine_count)}`}>
                    {formatTimeRemaining(bot.remaining_seconds)}
                  </div>
                  <div className="text-xs text-gray-400">
                    remaining
                  </div>
                </div>
              </div>
              
              {/* Progress Bar */}
              <div className="mt-3">
                <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div 
                    className={`h-full transition-all duration-1000 ${
                      bot.quarantine_count === 1 ? 'bg-yellow-400' :
                      bot.quarantine_count === 2 ? 'bg-orange-400' :
                      'bg-red-400'
                    }`}
                    style={{ width: `${Math.min(100, progressPercent)}%` }}
                  />
                </div>
              </div>
              
              {/* Next Action */}
              <div className="mt-3 flex items-center justify-between">
                <span className="text-xs text-gray-400">
                  Next Action:
                </span>
                <span className={`text-sm font-medium ${
                  bot.next_action === 'redeploy' ? 'text-green-400' : 'text-red-400'
                }`}>
                  {bot.next_action === 'redeploy' ? '🚀 Auto-Redeploy' : '🗑️ Delete & Regenerate'}
                </span>
              </div>
            </div>
          );
        })}
      </div>
      
      <div className="mt-6 p-4 bg-blue-900 bg-opacity-20 rounded border border-blue-500">
        <h4 className="text-sm font-semibold text-blue-300 mb-2">ℹ️ Quarantine Policy</h4>
        <ul className="text-xs text-gray-300 space-y-1">
          <li>• 1st pause → 1 hour retraining</li>
          <li>• 2nd pause → 3 hours retraining</li>
          <li>• 3rd pause → 24 hours retraining</li>
          <li>• 4th pause → Bot deleted & auto-regenerated</li>
        </ul>
      </div>
    </div>
  );
};

export default BotQuarantineSection;
