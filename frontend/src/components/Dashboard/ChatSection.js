import React, { useRef, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { API_BASE } from '../../lib/api.js';

const API = API_BASE;
// Admin password is verified on backend only - no hardcoded password in frontend
// Backend validates against ADMIN_PASSWORD environment variable

export const ChatSection = ({ 
  chatMessages, 
  setChatMessages, 
  chatInput, 
  setChatInput,
  token,
  showAdmin,
  setShowAdmin,
  awaitingPassword,
  setAwaitingPassword,
  adminAction,
  setAdminAction
}) => {
  const chatEndRef = useRef(null);
  const axiosConfig = { headers: { Authorization: `Bearer ${token}` } };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  const handleChatSubmit = async (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const originalInput = chatInput;
    const msgLower = chatInput.toLowerCase().trim();
    
    setChatMessages(prev => [...prev, { role: 'user', content: originalInput }]);
    setChatInput('');

    // Handle admin password - FIX: Use originalInput instead of cleared chatInput
    if (awaitingPassword) {
      // Send password to backend for validation (no client-side password check)
      try {
        // Backend validates password against ADMIN_PASSWORD environment variable
        await axios.post(`${API}/admin/unlock`, { password: originalInput }, axiosConfig);
        
        if (adminAction === 'show') {
          setShowAdmin(true);
          sessionStorage.setItem('adminPanelVisible', 'true');
          setChatMessages(prev => [...prev, { 
            role: 'assistant', 
            content: '✅ Admin panel activated. You now have access to system administration features.' 
          }]);
        } else if (adminAction === 'hide') {
          setShowAdmin(false);
          sessionStorage.removeItem('adminPanelVisible');
          setChatMessages(prev => [...prev, { 
            role: 'assistant', 
            content: '✅ Admin panel hidden.' 
          }]);
        }
        setAwaitingPassword(false);
        setAdminAction(null);
      } catch (error) {
        setChatMessages(prev => [...prev, { 
          role: 'assistant', 
          content: '❌ Invalid admin password. Please try again.' 
        }]);
        setAwaitingPassword(false);
        setAdminAction(null);
      }
      return;
    }

    // Handle 'show admin' command
    if (msgLower === 'show admin' || msgLower === 'show admn') {
      setAwaitingPassword(true);
      setAdminAction('show');
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'Please enter the admin password to show the admin section.' 
      }]);
      return;
    }

    // Handle 'hide admin' command
    if (msgLower === 'hide admin') {
      setAwaitingPassword(true);
      setAdminAction('hide');
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'Please enter the admin password to hide the admin section.' 
      }]);
      return;
    }

    // Send to AI
    try {
      const res = await axios.post(`${API}/ai/chat`, { content: originalInput }, axiosConfig);
      const reply = typeof res.data === 'string' 
        ? res.data 
        : (res.data.response || res.data.reply || res.data.message || 'No response');
      setChatMessages(prev => [...prev, { role: 'assistant', content: reply }]);
    } catch (err) {
      console.error('Chat error:', err);
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `AI error: ${err.message}` 
      }]);
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {chatMessages.map((msg, idx) => (
          <div key={idx} className={`chat-message ${msg.role}`}>
            <div className="message-content">{msg.content}</div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>
      
      <form onSubmit={handleChatSubmit} className="chat-input-form">
        <input
          type="text"
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          placeholder={awaitingPassword ? "Enter admin password..." : "Ask AI anything or give commands..."}
          className="chat-input"
        />
        <button type="submit" className="chat-send-btn">
          Send
        </button>
      </form>
    </div>
  );
};
