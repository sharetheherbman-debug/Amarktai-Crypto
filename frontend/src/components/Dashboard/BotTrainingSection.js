import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { get, post, notifyError } from '../../lib/apiClient';

const BotTrainingSection = () => {
  const [trainingHistory, setTrainingHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetchTrainingHistory();
  }, []);
  
  const fetchTrainingHistory = async () => {
    try {
      const data = await get('/training/history');
      setTrainingHistory(data.history || []);
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch training history:', error);
      notifyError(error);
      setLoading(false);
    }
  };
  
  const startTraining = async (botId) => {
    try {
      await post('/training/start', { bot_id: botId });
      toast.success('Training started successfully');
      fetchTrainingHistory();
    } catch (error) {
      console.error('Failed to start training:', error);
      toast.error('Failed to start training');
      notifyError(error);
    }
  };
  
  if (loading) {
    return (
      <div className="glass-panel p-6">
        <div className="animate-pulse">Loading training data...</div>
      </div>
    );
  }
  
  return (
    <div className="glass-panel p-6">
      <h3 className="text-xl font-bold mb-4 text-blue-400">
        🎓 Bot Training & Learning
      </h3>
      
      <div className="mb-6">
        <h4 className="text-lg font-semibold mb-3 text-white">Training History</h4>
        
        {trainingHistory.length === 0 ? (
          <p className="text-gray-400">No training history available.</p>
        ) : (
          <div className="space-y-3">
            {trainingHistory.map((training, idx) => (
              <div key={idx} className="bg-black bg-opacity-30 p-4 rounded-lg">
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
      
      <div className="mt-6 p-4 bg-blue-900 bg-opacity-20 rounded border border-blue-500">
        <h4 className="text-sm font-semibold text-blue-300 mb-2">ℹ️ Training Info</h4>
        <p className="text-xs text-gray-300">
          Bots automatically enter training when quarantined. Training helps bots learn from past mistakes and improve performance.
        </p>
      </div>
    </div>
  );
};

export default BotTrainingSection;
