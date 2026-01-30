import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, AlertTriangle, CheckCircle } from 'lucide-react';

/**
 * AI Chat Panel Component
 * Real-time AI chat with action confirmation
 */
const AIChatPanel = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [systemState, setSystemState] = useState(null);
  const [sessionChecked, setSessionChecked] = useState(false);
  const [showLoadHistory, setShowLoadHistory] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Check for fresh session and load greeting or history
  useEffect(() => {
    if (!sessionChecked) {
      checkSessionAndLoad();
      setSessionChecked(true);
    }
  }, [sessionChecked]);

  const checkSessionAndLoad = async () => {
    try {
      // Always show greeting on fresh login
      // Old messages must NOT render by default
      // Users can click "Load previous chat" to fetch history
      await fetchDailyGreeting();
      
      // Show "Load previous chat" button if there's history
      setShowLoadHistory(true);
    } catch (err) {
      console.error('Session check error:', err);
      // Show empty state - user can click load history
      setShowLoadHistory(true);
    }
  };

  const fetchDailyGreeting = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/ai/chat/greeting', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      const data = await response.json();
      
      const newMessages = [];
      
      // Always show only the greeting, never auto-load old messages
      if (data.content) {
        newMessages.push({
          role: 'assistant',
          content: data.content,
          timestamp: data.timestamp,
          is_greeting: true
        });
        
        if (data.system_state) {
          setSystemState(data.system_state);
        }
      }
      
      // Fetch and display since-last-login report
      try {
        const sinceLoginResponse = await fetch('/api/system/since-last-login', {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });
        
        if (sinceLoginResponse.ok) {
          const sinceData = await sinceLoginResponse.json();
          const reportContent = formatSinceLastLoginReport(sinceData);
          
          newMessages.push({
            role: 'assistant',
            content: reportContent,
            timestamp: new Date().toISOString(),
            is_greeting: false
          });
        }
      } catch (sinceErr) {
        console.error('Failed to fetch since-last-login:', sinceErr);
      }
      
      setMessages(newMessages);
    } catch (err) {
      console.error('Failed to fetch daily greeting:', err);
      // Show fallback greeting
      setMessages([{
        role: 'assistant',
        content: 'Welcome! I\'m your AI trading assistant. Ask me about your bots, performance, or system status.',
        timestamp: new Date().toISOString(),
        is_greeting: true
      }]);
    } finally {
      setLoading(false);
    }
  };

  const formatSinceLastLoginReport = (data) => {
    if (!data) return 'No activity since your last login.';
    
    let report = '📊 **Since Your Last Login:**\n\n';
    
    if (data.new_trades && data.new_trades > 0) {
      report += `✅ **${data.new_trades} new trades** executed\n`;
    }
    
    if (data.profit_change !== undefined && data.profit_change !== 0) {
      const profitSign = data.profit_change > 0 ? '+' : '';
      const profitColor = data.profit_change > 0 ? '📈' : '📉';
      report += `${profitColor} Profit: **${profitSign}R${data.profit_change.toFixed(2)}**\n`;
    }
    
    if (data.bot_status_changes && data.bot_status_changes.length > 0) {
      report += `\n🤖 **Bot Status Changes:**\n`;
      data.bot_status_changes.forEach(change => {
        report += `  • ${change.bot_name}: ${change.old_status} → ${change.new_status}\n`;
      });
    }
    
    if (data.alerts && data.alerts.length > 0) {
      report += `\n⚠️ **${data.alerts.length} new alerts**\n`;
      data.alerts.slice(0, 3).forEach(alert => {
        report += `  • ${alert.message}\n`;
      });
      if (data.alerts.length > 3) {
        report += `  • ... and ${data.alerts.length - 3} more\n`;
      }
    }
    
    if (data.errors && data.errors.length > 0) {
      report += `\n🔴 **${data.errors.length} errors occurred**\n`;
    }
    
    if (!data.new_trades && !data.bot_status_changes?.length && !data.alerts?.length) {
      report += 'No significant activity.\n';
    }
    
    if (data.last_login_time) {
      report += `\n🕒 Last login: ${new Date(data.last_login_time).toLocaleString()}`;
    }
    
    return report;
  };

  const loadRecentMessages = async () => {
    try {
      const response = await fetch('/api/ai/chat/history?limit=10', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      const data = await response.json();
      if (data.messages) {
        setMessages(data.messages);
      }
    } catch (err) {
      console.error('Failed to load recent messages:', err);
    }
  };

  const loadChatHistory = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/ai/chat/history', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      const data = await response.json();
      if (data.messages && data.messages.length > 0) {
        setMessages(data.messages);
        setShowLoadHistory(false); // Hide button after loading
      }
    } catch (err) {
      console.error('Failed to load chat history:', err);
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async () => {
    if (!input.trim()) return;

    // Content filter: Block admin-related queries
    const lowerInput = input.toLowerCase();
    const blockedPhrases = [
      'admin password',
      'show admin',
      'admin panel',
      'admin access',
      'admin credentials',
      'admin login',
      'unlock admin',
      'admin unlock'
    ];
    
    const containsBlockedPhrase = blockedPhrases.some(phrase => lowerInput.includes(phrase));
    
    if (containsBlockedPhrase) {
      setMessages(prev => [...prev, {
        role: 'user',
        content: input,
        timestamp: new Date().toISOString()
      }, {
        role: 'assistant',
        content: '⚠️ I cannot help with admin panel access or passwords. Admin features require secure authentication through the proper channels. Please contact support if you need assistance.',
        timestamp: new Date().toISOString(),
        error: true
      }]);
      setInput('');
      return;
    }

    const userMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          content: input,
          request_action: true  // Allow AI to propose actions
        })
      });

      const data = await response.json();

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.content,
        timestamp: data.timestamp
      }]);

      if (data.system_state) {
        setSystemState(data.system_state);
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err.message}. Please try again.`,
        timestamp: new Date().toISOString(),
        error: true
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const formatMessage = (content) => {
    // Format markdown-style messages
    return content
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.*?)`/g, '<code class="bg-gray-100 px-1 rounded">$1</code>')
      .replace(/⚠️/g, '<span class="text-yellow-600">⚠️</span>')
      .replace(/✅/g, '<span class="text-green-600">✅</span>');
  };

  const clearUIMessages = () => {
    // Clear UI only (backend history is preserved)
    setMessages([]);
    setSessionChecked(false);
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-lg shadow-lg">
      {/* Header */}
      <div className="px-4 py-3 border-b bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-t-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bot size={24} />
            <div>
              <h3 className="font-semibold">AI Trading Assistant</h3>
              <p className="text-xs opacity-90">Ask me anything about your trading system</p>
            </div>
          </div>
          <button
            onClick={clearUIMessages}
            className="text-xs px-2 py-1 bg-white/20 hover:bg-white/30 rounded transition"
            title="Clear UI (history preserved)"
          >
            Clear
          </button>
        </div>
      </div>

      {/* System State Summary */}
      {systemState && (
        <div className="px-4 py-2 bg-blue-50 border-b text-sm">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <span className="text-gray-600">Bots:</span>{' '}
              <span className="font-semibold">{systemState.bots.active}/{systemState.bots.total}</span>
            </div>
            <div>
              <span className="text-gray-600">Capital:</span>{' '}
              <span className="font-semibold">R{systemState.capital.total.toLocaleString()}</span>
            </div>
            <div>
              <span className="text-gray-600">Profit:</span>{' '}
              <span className={`font-semibold ${systemState.capital.total_profit >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                R{systemState.capital.total_profit.toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Load Previous Chat Button */}
        {showLoadHistory && messages.length <= 1 && (
          <div className="text-center mb-4">
            <button
              onClick={loadChatHistory}
              disabled={loading}
              className="px-4 py-2 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg hover:from-purple-700 hover:to-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold"
            >
              📜 Load Previous Chat History
            </button>
          </div>
        )}

        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-8">
            <Bot size={48} className="mx-auto mb-4 opacity-50" />
            <p>Start a conversation with your AI assistant!</p>
            <p className="text-sm mt-2">Try asking:</p>
            <ul className="text-sm mt-2 space-y-1">
              <li>"How are my bots performing?"</li>
              <li>"Show me my trade limits"</li>
              <li>"Should I pause any bots?"</li>
            </ul>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="flex-shrink-0">
                <div className="w-8 h-8 rounded-full bg-gradient-to-r from-blue-600 to-purple-600 flex items-center justify-center">
                  <Bot size={16} className="text-white" />
                </div>
              </div>
            )}

            <div
              className={`max-w-[70%] rounded-lg px-4 py-2 ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : msg.error
                  ? 'bg-red-50 text-red-900 border border-red-200'
                  : msg.is_greeting
                  ? 'bg-gradient-to-r from-green-50 to-blue-50 text-gray-900 border border-green-200'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              {msg.is_greeting && (
                <div className="text-xs font-semibold text-green-600 mb-1 flex items-center gap-1">
                  <CheckCircle size={12} />
                  Daily Report
                </div>
              )}
              <div
                className="text-sm whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: formatMessage(msg.content) }}
              />
              <div className="text-xs opacity-70 mt-1">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </div>
            </div>

            {msg.role === 'user' && (
              <div className="flex-shrink-0">
                <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center">
                  <User size={16} className="text-white" />
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-3 justify-start">
            <div className="flex-shrink-0">
              <div className="w-8 h-8 rounded-full bg-gradient-to-r from-blue-600 to-purple-600 flex items-center justify-center">
                <Bot size={16} className="text-white" />
              </div>
            </div>
            <div className="bg-gray-100 rounded-lg px-4 py-2">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t bg-gray-50 rounded-b-lg">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask your AI assistant..."
            className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <Send size={16} />
            <span className="hidden sm:inline">Send</span>
          </button>
        </div>
        <div className="text-xs text-gray-500 mt-2">
          <AlertTriangle size={12} className="inline mr-1" />
          AI can suggest actions. Dangerous actions require confirmation.
        </div>
      </div>
    </div>
  );
};

export default AIChatPanel;
