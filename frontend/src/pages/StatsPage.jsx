import { useState } from 'react';
import './StatsPage.css';

const PERIODS = [
  { key: 'today', label: 'Сегодня' },
  { key: '7',     label: '7 дней' },
  { key: '30',    label: '30 дней' },
  { key: '90',    label: '90 дней' },
  { key: 'all',   label: 'Всё время' },
];

const TIMELINE_DAYS = { today: 1, '7': 7, '30': 30, '90': 90, all: 30 };
const TIMELINE_TITLE = {
  today: 'Динамика за сегодня',
  '7':   'Динамика за 7 дней',
  '30':  'Динамика за 30 дней',
  '90':  'Динамика за 90 дней',
  all:   'Динамика (последние 30 дней)',
};

const STATUS_LABEL = {
  open: 'Открыто',
  in_progress: 'В работе',
  needs_operator: 'Ожидает оператора',
  closed: 'Закрыто',
};
const STATUS_COLOR = {
  open: '#3b82f6',
  in_progress: '#f59e0b',
  needs_operator: '#f97316',
  closed: '#22c55e',
};
const CATEGORY_LABEL = {
  malfunction: 'Неисправность',
  calibration: 'Калибровка',
  documentation: 'Документация',
  breakdown: 'Поломка',
  other: 'Другое',
};
const CATEGORY_COLOR = {
  malfunction: '#f59e0b',
  calibration: '#3b82f6',
  documentation: '#8b5cf6',
  breakdown: '#ef4444',
  other: '#94a3b8',
};
const SENTIMENT_LABEL = {
  positive: 'Позитивный',
  neutral: 'Нейтральный',
  negative: 'Негативный',
};
const SENTIMENT_COLOR = {
  positive: '#22c55e',
  neutral: '#94a3b8',
  negative: '#ef4444',
};

const PALETTE = ['#3b82f6', '#f59e0b', '#22c55e', '#8b5cf6', '#ef4444', '#06b6d4', '#f97316', '#ec4899'];

function filterByPeriod(tickets, period) {
  if (period === 'all') return tickets;
  const now = new Date();
  let cutoff;
  if (period === 'today') {
    cutoff = new Date(now);
    cutoff.setUTCHours(0, 0, 0, 0);
  } else {
    cutoff = new Date(now);
    cutoff.setDate(cutoff.getDate() - parseInt(period));
  }
  return tickets.filter(t => {
    const ts = t.created_at || t.date_received;
    return ts && new Date(ts) >= cutoff;
  });
}

function count(tickets, key) {
  return tickets.reduce((acc, t) => {
    const val = t[key] || 'other';
    acc[val] = (acc[val] || 0) + 1;
    return acc;
  }, {});
}

function countByDay(tickets, days) {
  const result = [];
  const now = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setUTCDate(d.getUTCDate() - i);
    const dayStr = d.toISOString().slice(0, 10);
    const label = `${String(d.getUTCDate()).padStart(2, '0')}.${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
    const value = tickets.filter(t => {
      const ts = t.created_at || t.date_received || '';
      return ts.slice(0, 10) === dayStr;
    }).length;
    result.push({ label, value });
  }
  return result;
}

function countDeviceType(tickets) {
  const raw = tickets.reduce((acc, t) => {
    const val = t.device_type || 'Не указан';
    acc[val] = (acc[val] || 0) + 1;
    return acc;
  }, {});
  return Object.fromEntries(
    Object.entries(raw).sort((a, b) => b[1] - a[1]).slice(0, 8)
  );
}

function BarChart({ data, labels, colors, total }) {
  return (
    <div className="stats-bars">
      {Object.entries(data).map(([key, val]) => (
        <div key={key} className="stats-bar-row">
          <span className="stats-bar-label">{labels[key] || key}</span>
          <div className="stats-bar-track">
            <div
              className="stats-bar-fill"
              style={{ width: `${(val / total) * 100}%`, background: colors[key] || '#94a3b8' }}
            />
          </div>
          <span className="stats-bar-count">{val}</span>
        </div>
      ))}
    </div>
  );
}

function DonutChart({ data, colors, total }) {
  const segments = [];
  let offset = 0;
  const r = 40;
  const circ = 2 * Math.PI * r;

  Object.entries(data).forEach(([key, val]) => {
    const pct = val / total;
    segments.push({ key, val, pct, offset });
    offset += pct;
  });

  return (
    <svg viewBox="0 0 100 100" className="stats-donut">
      {segments.map(({ key, pct, offset }) => (
        <circle
          key={key}
          cx="50" cy="50" r={r}
          fill="none"
          stroke={colors[key] || '#94a3b8'}
          strokeWidth="18"
          strokeDasharray={`${pct * circ} ${circ}`}
          strokeDashoffset={-offset * circ}
          transform="rotate(-90 50 50)"
        />
      ))}
      <text x="50" y="54" textAnchor="middle" className="stats-donut-total">{total}</text>
    </svg>
  );
}

function TimelineChart({ data }) {
  const max = Math.max(...data.map(d => d.value), 1);
  const W = 400, H = 80, padL = 8, padR = 8, padT = 10, padB = 4;
  const w = W - padL - padR;
  const h = H - padT - padB;
  const n = data.length;

  const points = data.map((d, i) => ({
    x: padL + (n > 1 ? (i / (n - 1)) * w : w / 2),
    y: padT + (1 - d.value / max) * h,
    ...d,
  }));

  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const areaD = `${pathD} L ${points[n - 1].x.toFixed(1)} ${(padT + h).toFixed(1)} L ${points[0].x.toFixed(1)} ${(padT + h).toFixed(1)} Z`;

  const step = Math.ceil(n / 7);
  const labelIdxs = new Set(points.map((_, i) => i).filter(i => i % step === 0));
  labelIdxs.add(n - 1);

  return (
    <div className="stats-timeline">
      <svg viewBox={`0 0 ${W} ${H}`} className="stats-timeline-svg" preserveAspectRatio="none">
        <defs>
          <linearGradient id="tl-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#2563eb" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaD} fill="url(#tl-grad)" />
        <path d={pathD} fill="none" stroke="#2563eb" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill="#2563eb" />
        ))}
      </svg>
      <div className="stats-timeline-labels">
        {points.map((p, i) =>
          labelIdxs.has(i) ? (
            <span
              key={i}
              className="stats-timeline-label"
              style={{ left: `${(p.x / W) * 100}%` }}
            >
              {p.label}
            </span>
          ) : null
        )}
      </div>
    </div>
  );
}

export default function StatsPage({ tickets }) {
  const [period, setPeriod] = useState('all');

  const filtered = filterByPeriod(tickets, period);
  const total = filtered.length;

  const byStatus   = count(filtered, 'status');
  const byCategory = count(filtered, 'category');
  const bySentiment = count(filtered, 'sentiment');
  const timelineDays = TIMELINE_DAYS[period];
  const byDays     = countByDay(filtered, timelineDays);
  const byDevice   = countDeviceType(filtered);
  const deviceTotal = Object.values(byDevice).reduce((a, b) => a + b, 0);
  const deviceColors = Object.fromEntries(
    Object.keys(byDevice).map((k, i) => [k, PALETTE[i % PALETTE.length]])
  );

  const closedCount   = byStatus['closed'] || 0;
  const resolutionRate = total > 0 ? Math.round((closedCount / total) * 100) : 0;
  const negativeCount  = bySentiment['negative'] || 0;
  const negativeRate   = total > 0 ? Math.round((negativeCount / total) * 100) : 0;

  return (
    <div className="stats-page">
      <div className="stats-header">
        <div className="stats-header-top">
          <div>
            <h2 className="stats-title">Статистика</h2>
            <p className="stats-subtitle">Сводная аналитика по обращениям</p>
          </div>
          <div className="stats-period">
            {PERIODS.map(p => (
              <button
                key={p.key}
                className={`stats-period-btn${period === p.key ? ' stats-period-btn--active' : ''}`}
                onClick={() => setPeriod(p.key)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {total === 0 ? (
        <div className="stats-empty">
          {tickets.length === 0 ? 'Нет данных для отображения' : 'Нет обращений за выбранный период'}
        </div>
      ) : (
        <>
          <div className="stats-kpis">
            <div className="stats-kpi">
              <span className="stats-kpi-value">{total}</span>
              <span className="stats-kpi-label">Всего обращений</span>
            </div>
            <div className="stats-kpi">
              <span className="stats-kpi-value" style={{ color: '#3b82f6' }}>{byStatus['open'] || 0}</span>
              <span className="stats-kpi-label">Открытых</span>
            </div>
            <div className="stats-kpi">
              <span className="stats-kpi-value" style={{ color: '#f59e0b' }}>{byStatus['in_progress'] || 0}</span>
              <span className="stats-kpi-label">В работе</span>
            </div>
            <div className="stats-kpi">
              <span className="stats-kpi-value" style={{ color: '#22c55e' }}>{closedCount}</span>
              <span className="stats-kpi-label">Закрытых</span>
            </div>
            <div className="stats-kpi">
              <span className="stats-kpi-value">{resolutionRate}%</span>
              <span className="stats-kpi-label">Решено</span>
            </div>
            <div className="stats-kpi">
              <span className="stats-kpi-value" style={{ color: negativeRate > 30 ? '#ef4444' : '#1e3a8a' }}>
                {negativeRate}%
              </span>
              <span className="stats-kpi-label">Негативных</span>
            </div>
          </div>

          <div className="stats-grid">
            <div className="stats-card">
              <div className="stats-card-title">По статусу</div>
              <div className="stats-card-body stats-card-body--donut">
                <DonutChart data={byStatus} colors={STATUS_COLOR} total={total} />
                <div className="stats-legend">
                  {Object.entries(byStatus).map(([key, val]) => (
                    <div key={key} className="stats-legend-row">
                      <span className="stats-legend-dot" style={{ background: STATUS_COLOR[key] || '#94a3b8' }} />
                      <span className="stats-legend-label">{STATUS_LABEL[key] || key}</span>
                      <span className="stats-legend-val">{val}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="stats-card">
              <div className="stats-card-title">По категории</div>
              <div className="stats-card-body">
                <BarChart data={byCategory} labels={CATEGORY_LABEL} colors={CATEGORY_COLOR} total={total} />
              </div>
            </div>

            <div className="stats-card">
              <div className="stats-card-title">По тональности</div>
              <div className="stats-card-body stats-card-body--donut">
                <DonutChart data={bySentiment} colors={SENTIMENT_COLOR} total={total} />
                <div className="stats-legend">
                  {Object.entries(bySentiment).map(([key, val]) => (
                    <div key={key} className="stats-legend-row">
                      <span className="stats-legend-dot" style={{ background: SENTIMENT_COLOR[key] || '#94a3b8' }} />
                      <span className="stats-legend-label">{SENTIMENT_LABEL[key] || key}</span>
                      <span className="stats-legend-val">{val}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="stats-grid stats-grid--bottom">
            <div className="stats-card">
              <div className="stats-card-title">{TIMELINE_TITLE[period]}</div>
              <div className="stats-card-body">
                <TimelineChart data={byDays} />
              </div>
            </div>

            <div className="stats-card">
              <div className="stats-card-title">По типу устройства</div>
              <div className="stats-card-body">
                <BarChart data={byDevice} labels={{}} colors={deviceColors} total={deviceTotal} />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
