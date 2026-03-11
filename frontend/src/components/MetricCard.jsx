export default function MetricCard({ label, value, testId }) {
  return (
    <div
      className="border-2 border-stone-300 bg-card p-5 transition-all hover:-translate-y-0.5 hover:-translate-x-0.5 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,0.12)]"
      data-testid={testId}
    >
      <p className="text-xs uppercase tracking-[0.2em] text-stone-500">{label}</p>
      <p className="font-mono text-3xl mt-2" data-testid={`${testId}-value`}>
        {value}
      </p>
    </div>
  );
}
