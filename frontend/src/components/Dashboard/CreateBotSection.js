import React, { useState } from 'react';
import { toast } from 'sonner';
import { post, notifyError } from '../../lib/apiClient';

export const CreateBotSection = ({ token, onBotCreated }) => {
  const [botName, setBotName] = useState('');
  const [botExchange, setBotExchange] = useState('luno');
  const [botCapital, setBotCapital] = useState('1000');
  const [botRisk, setBotRisk] = useState('safe');
  const [creating, setCreating] = useState(false);

  const handleCreateBot = async (e) => {
    e.preventDefault();
    
    if (!botName.trim()) {
      toast.error('Please enter a bot name');
      return;
    }

    if (parseFloat(botCapital) < 100) {
      toast.error('Minimum capital is R100');
      return;
    }

    setCreating(true);
    try {
      await post('/bots', {
        name: botName,
        initial_capital: parseFloat(botCapital),
        risk_mode: botRisk,
        exchange: botExchange
      });
      
      toast.success(`Bot "${botName}" created successfully!`);
      setBotName('');
      setBotCapital('1000');
      onBotCreated();
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to create bot';
      toast.error(msg);
      notifyError(err);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="create-bot-section">
      <h2 className="section-title">🤖 Create New Bot</h2>
      <form onSubmit={handleCreateBot} className="create-bot-form">
        <div className="form-row">
          <div className="form-group">
            <label>Bot Name</label>
            <input
              type="text"
              value={botName}
              onChange={(e) => setBotName(e.target.value)}
              placeholder="e.g., Zeus"
              required
            />
          </div>
          
          <div className="form-group">
            <label>Exchange</label>
            <select value={botExchange} onChange={(e) => setBotExchange(e.target.value)}>
              {platformOptions.map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Initial Capital (ZAR)</label>
            <input
              type="number"
              value={botCapital}
              onChange={(e) => setBotCapital(e.target.value)}
              min="100"
              step="100"
              required
            />
          </div>
          
          <div className="form-group">
            <label>Risk Mode</label>
            <select value={botRisk} onChange={(e) => setBotRisk(e.target.value)}>
              <option value="safe">Safe (Conservative)</option>
              <option value="balanced">Balanced (Moderate)</option>
              <option value="aggressive">Aggressive (High Risk)</option>
            </select>
          </div>
        </div>

        <button type="submit" className="btn-primary" disabled={creating}>
          {creating ? '⏳ Creating...' : '✅ Create Bot'}
        </button>
      </form>
    </div>
  );
};
