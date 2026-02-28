import './CategoryBadge.css';

const LABELS = {
  malfunction: 'Неисправность',
  calibration: 'Калибровка',
  documentation: 'Документация',
  breakdown: 'Поломка',
};

export default function CategoryBadge({ value }) {
  return (
    <span className={`category-badge category-badge--${value}`}>
      {LABELS[value] ?? value}
    </span>
  );
}
