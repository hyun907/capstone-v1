export function PlanView({ plan }: { plan: string }) {
  return (
    <section className="plan-card" aria-label="Supervisor 계획">
      <h2>계획</h2>
      <p>{plan}</p>
    </section>
  );
}
