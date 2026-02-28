import { useState, useEffect } from 'react';
import SentimentBadge from './SentimentBadge';
import CategoryBadge from './CategoryBadge';
import { updateTicketStatus, patchTicket, fetchAttachments, attachmentDownloadUrl } from '../api/tickets';
import './TicketForm.css';

const SENTIMENT_EMOJI = { positive: '😊', neutral: '😐', negative: '😠' };
const STATUS_LABEL = {
  open: 'Открыто 🆕',
  in_progress: 'В процессе ⏳',
  needs_operator: 'Нужна помощь оператора 🆘',
  closed: 'Закрыто ✅',
};

function fmt(dateStr) {
  return new Date(dateStr).toLocaleString('ru-RU');
}

export default function TicketForm({ ticket, onTicketUpdate }) {
  const [closing, setClosing] = useState(false);
  const [editing, setEditing] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [lightboxUrl, setLightboxUrl] = useState(null);

  useEffect(() => {
    if (!ticket) return;
    fetchAttachments(ticket.id)
      .then(setAttachments)
      .catch(() => setAttachments([]));
  }, [ticket?.id]);

  async function handleClose() {
    if (closing) return;
    setClosing(true);
    try {
      const updated = await updateTicketStatus(ticket.id, 'closed');
      if (onTicketUpdate) onTicketUpdate(updated);
    } finally {
      setClosing(false);
    }
  }

  function startEdit(field, value) {
    setEditing(field);
    setEditValue(value ?? '');
  }

  function cancelEdit() {
    setEditing(null);
    setEditValue('');
  }

  async function saveField(field, value) {
    if (saving) return;
    setSaving(true);
    try {
      const payload =
        field === 'device_serials'
          ? { device_serials: value.split(',').map((s) => s.trim()).filter(Boolean) }
          : { [field]: value || null };
      const updated = await patchTicket(ticket.id, payload);
      if (onTicketUpdate) onTicketUpdate(updated);
    } catch {
      // ignore
    } finally {
      setSaving(false);
      setEditing(null);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      saveField(editing, editValue);
    }
    if (e.key === 'Escape') cancelEdit();
  }

  // Returns <td> for an editable value cell
  function valCell(field, rawValue, opts = {}) {
    const { display, editType = 'text', wide = false } = opts;
    const isEditing = editing === field;
    const tdClass = [
      'tf-value-cell',
      wide ? 'tf-value-cell--wide' : '',
      'tf-value-cell--editable',
      isEditing ? 'tf-value-cell--editing' : '',
    ].filter(Boolean).join(' ');

    let content;
    if (isEditing) {
      if (editType === 'textarea') {
        content = (
          <textarea
            className="tf-edit-input tf-edit-textarea"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={() => saveField(field, editValue)}
            onKeyDown={(e) => { if (e.key === 'Escape') cancelEdit(); }}
            autoFocus
            disabled={saving}
          />
        );
      } else if (editType === 'select-sentiment') {
        content = (
          <select
            className="tf-edit-select"
            value={editValue}
            autoFocus
            disabled={saving}
            onChange={(e) => saveField(field, e.target.value)}
          >
            <option value="positive">😊 Позитивная</option>
            <option value="neutral">😐 Нейтральная</option>
            <option value="negative">😠 Негативная</option>
          </select>
        );
      } else if (editType === 'select-category') {
        content = (
          <select
            className="tf-edit-select"
            value={editValue}
            autoFocus
            disabled={saving}
            onChange={(e) => saveField(field, e.target.value)}
          >
            <option value="malfunction">Неисправность</option>
            <option value="calibration">Калибровка</option>
            <option value="documentation">Документация</option>
            <option value="breakdown">Поломка</option>
          </select>
        );
      } else {
        content = (
          <input
            className="tf-edit-input"
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={() => saveField(field, editValue)}
            onKeyDown={handleKeyDown}
            autoFocus
            disabled={saving}
          />
        );
      }
    } else {
      const shown =
        display !== undefined
          ? display
          : rawValue || <span className="tf-empty">—</span>;
      content = <span className="tf-editable-value">{shown}</span>;
    }

    return (
      <td
        className={tdClass}
        colSpan={wide ? 3 : undefined}
        onClick={!isEditing ? () => startEdit(field, rawValue ?? '') : undefined}
      >
        {content}
      </td>
    );
  }

  if (!ticket) {
    return (
      <div className="ticket-form ticket-form--empty">
        <div className="ticket-form-placeholder">
          <span className="tf-placeholder-icon">📋</span>
          <span>Выберите обращение из списка слева</span>
        </div>
      </div>
    );
  }

  return (
    <div className="ticket-form">
      <div className="ticket-form-header">
        <span className="ticket-form-id">Заявка #{ticket.id}</span>
        {ticket.status !== 'closed' && (
          <button className="tf-close-btn" onClick={handleClose} disabled={closing}>
            {closing ? 'Закрытие...' : '✓ Закрыть заявку'}
          </button>
        )}
        {ticket.status === 'closed' && (
          <span className="tf-closed-label">✅ Закрыта</span>
        )}
      </div>

      <div className="ticket-form-table-wrap">
        <table className="tf-table">
          <tbody>
            <tr>
              <td className="tf-label-cell">Дата поступления</td>
              <td className="tf-value-cell">{fmt(ticket.date_received)}</td>
              <td className="tf-label-cell">Статус</td>
              <td className="tf-value-cell">{STATUS_LABEL[ticket.status]}</td>
            </tr>
            <tr>
              <td className="tf-label-cell">ФИО отправителя</td>
              {valCell('full_name', ticket.full_name)}
              <td className="tf-label-cell">Email</td>
              {valCell('email', ticket.email)}
            </tr>
            <tr>
              <td className="tf-label-cell">Объект / предприятие</td>
              {valCell('company', ticket.company)}
              <td className="tf-label-cell">Телефон</td>
              {valCell('phone', ticket.phone)}
            </tr>
            <tr>
              <td className="tf-label-cell">Заводские номера</td>
              {valCell('device_serials', (ticket.device_serials || []).join(', '))}
              <td className="tf-label-cell">Тип приборов</td>
              {valCell('device_type', ticket.device_type)}
            </tr>
            <tr>
              <td className="tf-label-cell">Эмоциональный окрас</td>
              {valCell('sentiment', ticket.sentiment, {
                display: (
                  <span className="tf-sent-cell">
                    {SENTIMENT_EMOJI[ticket.sentiment]} <SentimentBadge value={ticket.sentiment} />
                  </span>
                ),
                editType: 'select-sentiment',
              })}
              <td className="tf-label-cell">Категория запроса</td>
              {valCell('category', ticket.category, {
                display: <CategoryBadge value={ticket.category} />,
                editType: 'select-category',
              })}
            </tr>
            <tr>
              <td className="tf-label-cell">Суть вопроса</td>
              {valCell('summary', ticket.summary, { editType: 'textarea', wide: true })}
            </tr>
            <tr>
              <td className="tf-label-cell">Оригинальное письмо</td>
              <td className="tf-value-cell tf-value-cell--wide" colSpan={3}>
                {ticket.original_email}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {attachments.length > 0 && (
        <div className="tf-attachments">
          <div className="tf-attachments-title">Вложения ({attachments.length})</div>
          <div className="tf-attachments-list">
            {attachments.map((att) => {
              const url = attachmentDownloadUrl(att.id);
              const isImage = att.content_type.startsWith('image/');
              return (
                <div key={att.id} className="tf-attachment-item">
                  {isImage ? (
                    <>
                      <img
                        className="tf-attachment-img"
                        src={url}
                        alt={att.filename}
                        onClick={() => setLightboxUrl(url)}
                      />
                      <span className="tf-attachment-name">{att.filename}</span>
                    </>
                  ) : (
                    <a
                      className="tf-attachment-file"
                      href={url}
                      download={att.filename}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <span className="tf-attachment-file-icon">📎</span>
                      <span>{att.filename}</span>
                    </a>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {lightboxUrl && (
        <div className="tf-lightbox" onClick={() => setLightboxUrl(null)}>
          <img src={lightboxUrl} alt="Просмотр" />
        </div>
      )}
    </div>
  );
}
