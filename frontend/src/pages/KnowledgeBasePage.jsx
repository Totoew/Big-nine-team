import { useState } from 'react';
import './KnowledgeBasePage.css';

const FAQ_ITEMS = [
  {
    q: 'Где найти разрешительную документацию?',
    a: 'Техническая и разрешительная документации доступны на странице библиотеки файлов компании.',
  },
  {
    q: 'Какой срок гарантии на оборудование?',
    a: 'Гарантийный срок составляет до 3-х лет и указан в руководствах по эксплуатации соответствующих приборов.',
  },
  {
    q: 'Как отправить оборудование в ремонт?',
    a: 'Необходимо направить сопроводительное письмо с описанием неисправности, указать наименование организации и контакты специалистов. Груз отправляется на имя организации ООО «ЭРИС» (адрес: Пермский край, г. Чайковский, ул. Промышленная, д. 8/25). Контактное лицо: Брюханова Наталья Олеговна.',
  },
  {
    q: 'Как получить прайс-лист?',
    a: 'Обратитесь в отдел продаж, написав письмо на адрес info@eriskip.ru.',
  },
  {
    q: 'Способы настройки датчика ДГС ЭРИС-210?',
    a: 'Установка нуля и калибровка производятся тремя способами: магнитом, по интерфейсу RS485 и по интерфейсу HART.',
  },
  {
    q: 'Какой интервал между поверками?',
    a: 'Сведения об интервалах находятся в федеральном информационном фонде по обеспечению единства измерений.',
  },
  {
    q: 'Что входит в комплект поставки датчиков?',
    a: 'В стандартную комплектацию входят: кабельный ввод, заглушка, магнитный ключ, шестигранник, паспорт на прибор.',
  },
  {
    q: 'Максимальный диаметр кабеля для ввода?',
    a: 'Для кабельного ввода А3RCCBF/20S-2/M20 максимальный диаметр наружной оболочки составляет 11,7 мм.',
  },
  {
    q: 'Где скачать DD файлы?',
    a: 'DD файлы доступны в разделе библиотеки файлов компании.',
  },
];

const MANUALS = [
  {
    title: 'Руководство по эксплуатации ДГС ЭРИС-230',
    size: '4.58 МБ',
    url: 'https://eriskip.com/uploads/files/en/1/120/dgs-230-manual-en.pdf',
  },
  {
    title: 'Руководство по эксплуатации ДГС ЭРИС-210',
    size: '4.12 МБ',
    url: 'https://eriskip.com/uploads/files/ru/1/121/dgs-210-manual-en.pdf',
  },
  {
    title: 'Руководство по эксплуатации ПГ ЭРИС-414',
    size: '1.07 МБ',
    url: 'https://eriskip.com/uploads/files/en/1/122/eris-pg-414-manual-en-v1.pdf',
  },
];

const SOLUTIONS = [
  {
    title: 'Техническое описание ДГС ЭРИС-230',
    size: '2.84 МБ',
    url: 'https://eriskip.com/uploads/files/en/1/199/dgs-eris-230.pdf',
  },
  {
    title: 'Техническое описание ДГС ЭРИС-210',
    size: '2.71 МБ',
    url: 'https://eriskip.com/uploads/files/en/1/198/dgs-eris-210.pdf',
  },
  {
    title: 'Техническое описание ПГ ЭРИС-414',
    size: '5.60 МБ',
    url: 'https://eriskip.com/uploads/files/en/4/204/pg-eris-414-a4.pdf',
  },
];

const SECTIONS = [
  {
    id: 'manuals',
    title: 'Руководства по эксплуатации',
    description: 'Технические руководства и инструкции по приборам ЭРИС',
    count: MANUALS.length,
    available: true,
  },
  {
    id: 'faq',
    title: 'Часто задаваемые вопросы',
    description: 'Типовые вопросы и готовые ответы для операторов',
    count: FAQ_ITEMS.length,
    available: true,
  },
  {
    id: 'solutions',
    title: 'База решений',
    description: 'Технические описания и справочные материалы по оборудованию',
    count: SOLUTIONS.length,
    available: true,
  },
];

function FilePanel({ title, files, onClose }) {
  return (
    <div className="kb-overlay" onClick={onClose}>
      <div className="kb-faq-panel" onClick={(e) => e.stopPropagation()}>
        <div className="kb-faq-panel-header">
          <span className="kb-faq-panel-title">{title}</span>
          <button className="kb-faq-close" onClick={onClose}>✕</button>
        </div>
        <div className="kb-file-list">
          {files.map((file, i) => (
            <div key={i} className="kb-file-item">
              <div className="kb-file-icon">PDF</div>
              <div className="kb-file-info">
                <div className="kb-file-title">{file.title}</div>
                <div className="kb-file-meta">{file.size}</div>
              </div>
              <a
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                className="kb-file-download"
              >
                Скачать
              </a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FaqPanel({ onClose }) {
  const [openIdx, setOpenIdx] = useState(null);

  return (
    <div className="kb-overlay" onClick={onClose}>
      <div className="kb-faq-panel" onClick={(e) => e.stopPropagation()}>
        <div className="kb-faq-panel-header">
          <span className="kb-faq-panel-title">Часто задаваемые вопросы</span>
          <button className="kb-faq-close" onClick={onClose}>✕</button>
        </div>
        <div className="kb-faq-list">
          {FAQ_ITEMS.map((item, i) => (
            <div
              key={i}
              className={`kb-faq-item ${openIdx === i ? 'kb-faq-item--open' : ''}`}
            >
              <button
                className="kb-faq-question"
                onClick={() => setOpenIdx(openIdx === i ? null : i)}
              >
                <span className="kb-faq-q-text">{item.q}</span>
                <span className="kb-faq-chevron">{openIdx === i ? '▲' : '▼'}</span>
              </button>
              {openIdx === i && (
                <div className="kb-faq-answer">{item.a}</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function KnowledgeBasePage() {
  const [openPanel, setOpenPanel] = useState(null);

  function handleCardClick(id) {
    setOpenPanel(id);
  }

  return (
    <div className="kb-page">
      <div className="kb-header">
        <h2 className="kb-title">База знаний</h2>
        <p className="kb-subtitle">Справочные материалы и инструкции для операторов службы поддержки</p>
      </div>

      <div className="kb-grid">
        {SECTIONS.map((section) => (
          <div
            key={section.id}
            className="kb-card kb-card--active"
            onClick={() => handleCardClick(section.id)}
          >
            <div className="kb-card-body">
              <div className="kb-card-title">{section.title}</div>
              <div className="kb-card-desc">{section.description}</div>
              <div className="kb-card-count">{section.count} {section.id === 'faq' ? 'вопросов' : 'файлов'}</div>
            </div>
          </div>
        ))}
      </div>

      {openPanel === 'manuals' && (
        <FilePanel
          title="Руководства по эксплуатации"
          files={MANUALS}
          onClose={() => setOpenPanel(null)}
        />
      )}
      {openPanel === 'faq' && (
        <FaqPanel onClose={() => setOpenPanel(null)} />
      )}
      {openPanel === 'solutions' && (
        <FilePanel
          title="База решений"
          files={SOLUTIONS}
          onClose={() => setOpenPanel(null)}
        />
      )}
    </div>
  );
}
