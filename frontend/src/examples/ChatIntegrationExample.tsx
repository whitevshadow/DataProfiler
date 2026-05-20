/**
 * Example: Chat Integration for DBML Viewer
 * 
 * This example shows how to integrate the DBML viewer into a chat interface.
 * When a user sends a message like "Display schema.dbml", the viewer is rendered inline.
 */

import React, { useState } from 'react';
import DBMLViewer from './components/DBMLViewer';

// Example message type
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  showDbml?: boolean;
}

// Example chat component
export function ChatIntegrationExample() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (!input.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
    };

    // Detect DBML viewer trigger
    const triggers = [
      'display schema.dbml',
      'show dbml',
      'render schema',
      'view schema diagram',
      'show er diagram',
      'display database schema',
    ];

    const shouldShowDbml = triggers.some(trigger =>
      input.toLowerCase().includes(trigger)
    );

    // Add user message
    setMessages(prev => [...prev, userMessage]);

    // Add assistant response with DBML viewer
    if (shouldShowDbml) {
      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Here is your database schema:',
        showDbml: true,
      };
      setMessages(prev => [...prev, assistantMessage]);
    } else {
      // Normal response
      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'This is a normal response...',
      };
      setMessages(prev => [...prev, assistantMessage]);
    }

    setInput('');
  };

  return (
    <div className="chat-container" style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* Messages Area */}
      <div className="messages-area" style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        {messages.map(msg => (
          <div key={msg.id} className={`message message-${msg.role}`}>
            <div className="message-header">
              <strong>{msg.role === 'user' ? 'You' : 'Assistant'}</strong>
            </div>
            <div className="message-content">
              {msg.content}
            </div>
            
            {/* Render DBML viewer if triggered */}
            {msg.showDbml && (
              <div style={{ marginTop: '16px' }}>
                <DBMLViewer onClose={() => {
                  // Optional: remove viewer on close
                  setMessages(prev => prev.map(m =>
                    m.id === msg.id ? { ...m, showDbml: false } : m
                  ));
                }} />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Input Area */}
      <div className="input-area" style={{ padding: '16px', borderTop: '1px solid #e0e0e0' }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyPress={e => e.key === 'Enter' && handleSend()}
            placeholder="Type a message..."
            style={{
              flex: 1,
              padding: '12px',
              border: '1px solid #d0d0d0',
              borderRadius: '8px',
              fontSize: '14px',
            }}
          />
          <button
            onClick={handleSend}
            style={{
              padding: '12px 24px',
              background: '#2196f3',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: 600,
            }}
          >
            Send
          </button>
        </div>
        <div style={{ marginTop: '8px', fontSize: '12px', color: '#666' }}>
          Try typing: "Display schema.dbml"
        </div>
      </div>
    </div>
  );
}

/**
 * Alternative: WebSocket-based Chat Integration
 */
export function WebSocketChatExample() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [ws, setWs] = useState<WebSocket | null>(null);

  // Connect to WebSocket
  React.useEffect(() => {
    const socket = new WebSocket('ws://localhost:5500/ws/chat');
    
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      // Check if response indicates DBML should be shown
      const assistantMessage: ChatMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: data.content,
        showDbml: data.show_dbml || false,
      };
      
      setMessages(prev => [...prev, assistantMessage]);
    };
    
    setWs(socket);
    
    return () => socket.close();
  }, []);

  const sendMessage = (content: string) => {
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content,
    };
    
    setMessages(prev => [...prev, userMessage]);
    
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ message: content }));
    }
  };

  return (
    <div className="chat-container">
      {/* Render messages with DBML viewer support */}
      {messages.map(msg => (
        <div key={msg.id}>
          <div>{msg.content}</div>
          {msg.showDbml && <DBMLViewer />}
        </div>
      ))}
    </div>
  );
}

/**
 * Minimal Example: Single Message with DBML
 */
export function MinimalExample() {
  return (
    <div style={{ padding: '20px' }}>
      <div className="message">
        <p><strong>Assistant:</strong> Here is your database schema:</p>
        <DBMLViewer />
      </div>
    </div>
  );
}
