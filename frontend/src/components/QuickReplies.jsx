const QUICK_REPLIES = [
  'Explore vehicles',
  'Check my test drive',
  'Booking status',
  'Service request',
];

export function QuickReplies({ onSelect, disabled }) {
  return (
    <div className="quick-replies" aria-label="Quick reply suggestions">
      {QUICK_REPLIES.map((label) => (
        <button
          key={label}
          type="button"
          className="quick-reply"
          onClick={() => onSelect(label)}
          disabled={disabled}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
