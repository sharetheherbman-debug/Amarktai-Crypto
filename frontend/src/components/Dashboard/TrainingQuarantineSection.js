import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { get, notifyError } from '../../lib/apiClient';

const TrainingQuarantineSection = () => {
  const [activeTab, setActiveTab] = useState('training'); // 'training' or 'quarantine'
  const [trainingHistory, setTrainingHistory] = useState([]);
  const [quarantinedBots, setQuarantinedBots] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // Update every 10s
    return () => clearInterval(interval);
  }, []);
  
  const fetchData = async () => {
    try {
      // Fetch training history
      const trainingResponse = await get('/training/history');
      setTrainingHistory(trainingResponse.history || []);
      
      // Fetch quarantine status
      const quarantineResponse = await get('/quarantine/status');
      setQuarantinedBots(quarantineResponse.quarantined_bots || []);
      
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch data:', error);
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
  
  return (
    <div className="glass-panel p-6">
      {/* Header with Tabs */}
      <div className="mb-6">
        <h3 className="text-xl font-bold mb-4 text-white">
          🎓 Training & Quarantine
        </h3>
        
        {/* Tab Navigation */}
        <div className="flex space-x-2 border-b border-gray-700">
          <button
            onClick={() => setActiveTab('training')}
            className={`px-4 py-2 font-semibold transition-colors ${
              activeTab === 'training'
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Training ({trainingHistory.length})
          </button>
          <button
            onClick={() => setActiveTab('quarantine')}
            className={`px-4 py-2 font-semibold transition-colors ${
              activeTab === 'quarantine'
                ? 'text-yellow-400 border-b-2 border-yellow-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Quarantine ({quarantinedBots.length})
          </button>
        </div>
      </div>
      
      {/* Tab Content */}
      {loading ? (
        <div className="animate-pulse text-gray-400">Loading...</div>
      ) : (
        <>
          {/* Training Tab */}
          {activeTab === 'training' && (
            <div>
              <div className="mb-4">
                <h4 className="text-lg font-semibold mb-3 text-white">Training History</h4>
                
                {trainingHistory.length === 0 ? (
                  <p className="text-gray-400">No training history available.</p>
                ) : (
                  <div className="space-y-3">
                    {trainingHistory.map((training, idx) => (
                      <div key={idx} className="bg-black bg-opacity-30 p-4 rounded-lg hover:bg-opacity-40 transition-all">
                        <div className="flex justify-between items-start">
                          <div>
                            <h5 className="font-semibold text-white">{training.bot_name}</h5>
                            <p className="text-sm text-gray-400">
                              Exchange: {training.exchange} • Mode: {training.mode}
                            </p>
                            <p className="text-xs text-gray-500 mt-1">
                              Duration: {training.duration} • Status: {training.status}
                            </p>
                          </div>
                          <div className="text-right">
                            <div className={`text-lg font-bold ${
                              training.final_pnl > 0 ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {training.final_pnl > 0 ? '+' : ''}{training.final_pnl}%
                            </div>
                            <div className="text-xs text-gray-400">P&L</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              
              <div className="mt-6 p-4 bg-blue-900 bg-opacity-20 rounded-lg border border-blue-500 border-opacity-30">
                <h5 className="font-semibold text-blue-300 mb-2">About Training</h5>
                <p className="text-sm text-gray-300">
                  Bots undergo a 7-day paper trading period to learn market patterns and validate strategies
                  before being eligible for live trading promotion. High-performing bots can be promoted to
                  live mode after meeting performance criteria.
                </p>
              </div>
            </div>
          )}
          
          {/* Quarantine Tab */}
          {activeTab === 'quarantine' && (
            <div>
              {quarantinedBots.length === 0 ? (
                <div>
                  <h4 className="text-lg font-semibold mb-3 text-green-400">
                    ✅ No Bots in Quarantine
                  </h4>
                  <p className="text-gray-400">All bots are operating normally.</p>
                </div>
              ) : (
                <>
                  <div className="space-y-4 mb-6">
                    {quarantinedBots.map((bot) => {
                      const progress = bot.max_attempt_duration > 0
                        ? ((bot.max_attempt_duration - bot.time_remaining) / bot.max_attempt_duration) * 100
                        : 0;
                      
                      return (
                        <div key={bot.bot_id} className="bg-black bg-opacity-30 p-4 rounded-lg border border-yellow-500 border-opacity-30">
                          <div className="flex justify-between items-start mb-3">
                            <div>
                              <h5 className="font-semibold text-white">{bot.bot_name}</h5>
                              <p className="text-sm text-gray-400">
                                Exchange: {bot.exchange} • Reason: {bot.pause_reason}
                              </p>
                            </div>
                            <div className={`text-sm font-semibold ${getQuarantineColor(bot.attempt_count)}`}>
                              Attempt {bot.attempt_count}/3
                            </div>
                          </div>
                          
                          {/* Progress Bar */}
                          <div className="mb-2">
                            <div className="flex justify-between text-xs text-gray-400 mb-1">
                              <span>Retraining Progress</span>
                              <span>{formatTimeRemaining(bot.time_remaining)} remaining</span>
                            </div>
                            <div className="w-full bg-gray-700 rounded-full h-2">
                              <div 
                                className={`h-2 rounded-full transition-all ${
                                  bot.attempt_count === 1 ? 'bg-yellow-400' :
                                  bot.attempt_count === 2 ? 'bg-orange-400' :
                                  'bg-red-400'
                                }`}
                                style={{ width: `${progress}%` }}
                              ></div>
                            </div>
                          </div>
                          
                          <div className="text-xs text-gray-400">
                            Next action: {bot.next_action || 'Auto-redeploy or regenerate'}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  
                  <div className="p-4 bg-yellow-900 bg-opacity-20 rounded-lg border border-yellow-500 border-opacity-30">
                    <h5 className="font-semibold text-yellow-300 mb-2">Quarantine Policy</h5>
                    <p className="text-sm text-gray-300">
                      Bots are placed in quarantine when they experience repeated errors, validation failures,
                      or poor performance. The system automatically retrains them with adjusted parameters.
                      After 3 failed attempts, bots are stopped and may need manual intervention.
                    </p>
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default TrainingQuarantineSection;
