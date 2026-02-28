import { useState, useEffect, useRef } from 'react';
import { fetchChat, postChatMessage, postAiMessage } from '../api/tickets';
import './ChatWindow.css';

const ROLE_AVATAR = { user: '👤', bot: '🤖', operator: '👨‍💼', ai_query: '👨‍💼' };

export default function ChatWindow({ ticket, onTicketUpdate }) {
  const [messages, setMessages] = useState([]);
  const [activeTab, setActiveTab] = useState('ai'); // 'ai' | 'client'
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (!ticket) { setMessages([]); return; }
    fetchChat(ticket.id).then(setMessages).catch(() => setMessages([]));
    setInput('');
  }, [ticket?.id]);

  useEffect(() => {
    if (ticket?.id) {
      fetchChat(ticket.id).then(setMessages).catch(() => {});
    }
  }, [ticket?.status]);

  // Poll for new messages every 10 seconds — update only if count increased
  useEffect(() => {
    if (!ticket?.id) return;
    const id = setInterval(() => {
      fetchChat(ticket.id).then((data) => {
        setMessages((prev) => data.length > prev.length ? data : prev);
      }).catch(() => {});
    }, 10000);
    return () => clearInterval(id);
  }, [ticket?.id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activeTab]);

  // AI tab: client email as context + AI responses + operator questions to AI
  const aiMessages = messages.filter((m) => ['user', 'bot', 'ai_query'].includes(m.role));
  // Client tab: client emails + operator responses (sent to client)
  const clientMessages = messages.filter((m) => ['user', 'operator'].includes(m.role));
  const displayMessages = activeTab === 'ai' ? aiMessages : clientMessages;

  async function handleSend() {
    const text = input.trim();
    if (!text || sending || !ticket || ticket.status === 'closed') return;
    setSending(true);
    setInput('');

    try {
      if (activeTab === 'ai') {
        // Send to AI: saves ai_query + bot response, no email to client
        await postAiMessage(ticket.id, text);
        const updated = await fetchChat(ticket.id);
        setMessages(updated);
      } else {
        // Send to client: emails them, then refetch to get canonical state
        await postChatMessage(ticket.id, 'operator', text);
        const updated = await fetchChat(ticket.id);
        setMessages(updated);
      }
    } catch {
      // ignore
    } finally {
      setSending(false);
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (!ticket) {
    return (
      <div className="chat-window chat-window--empty">
        <span className="chat-empty-text">Выберите обращение для просмотра чата</span>
      </div>
    );
  }

  return (
    <div className="chat-window">
      <div className="chat-tabs">
        <button
          className={`chat-tab-btn ${activeTab === 'ai' ? 'chat-tab-btn--active' : ''}`}
          onClick={() => { setActiveTab('ai'); setInput(''); }}
        >
          ИИ-ассистент
        </button>
        <button
          className={`chat-tab-btn ${activeTab === 'client' ? 'chat-tab-btn--active' : ''}`}
          onClick={() => { setActiveTab('client'); setInput(''); }}
        >
          Клиент
          {ticket?.status === 'needs_operator' && (
            <span className="chat-tab-badge">!</span>
          )}
        </button>
      </div>

      <div className="chat-messages">
        {displayMessages.map((msg, i) => {
          // In AI tab: operator's questions (ai_query) are outgoing (RIGHT)
          // In client tab: operator's messages to client are outgoing (RIGHT)
          const isOutgoing = activeTab === 'ai'
            ? msg.role === 'ai_query'
            : msg.role === 'operator';

          return (
            <div
              key={msg.id || i}
              className={`chat-bubble chat-bubble--${msg.role} ${isOutgoing ? 'chat-bubble--out' : 'chat-bubble--in'}`}
            >
              {!isOutgoing && (
                <span className="chat-avatar">{ROLE_AVATAR[msg.role] ?? '👤'}</span>
              )}
              <div className="chat-text">{msg.text}</div>
              {isOutgoing && (
                <span className="chat-avatar">{ROLE_AVATAR[msg.role] ?? '👨‍💼'}</span>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {ticket?.status === 'closed' ? (
        <div className="chat-locked">Заявка закрыта</div>
      ) : (
        <div className="chat-input-row">
          <textarea
            className="chat-input"
            placeholder={
              activeTab === 'ai'
                ? 'Задайте вопрос ИИ-ассистенту...'
                : 'Введите ответ клиенту...'
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            rows={1}
            disabled={sending}
          />
          <button
            className={`chat-send-btn ${activeTab === 'ai' ? 'chat-send-btn--ai' : ''}`}
            onClick={handleSend}
            disabled={!input.trim() || sending}
          >
            {sending ? '...' : 'Отправить'}
          </button>
        </div>
      )}
    </div>
  );
}
