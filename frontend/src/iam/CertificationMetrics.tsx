import { t } from "../i18n";

export interface Certification {
  campaigns: number; decisions: number; completed: number;
  pending: number; revoked: number; overdue: number; completion: number | null;
}

export function CertificationMetrics({ result }: { result: Certification }) {
  if (!result.campaigns) return <p>{t("No certification campaigns yet. Open campaigns to plan your first review.")}</p>;
  const labels = [
    ["Total review decisions", result.decisions], ["Completed reviews", result.completed],
    ["Pending reviews", result.pending], ["Revoked access", result.revoked], ["Overdue reviews", result.overdue],
    ["Completion percentage", result.completion === null ? "—" : `${result.completion}%`],
  ] as const;
  return <dl className="operations-grid">{labels.map(([label, count]) => <div key={label} className="operations-tile">
    <dt>{t(label)}</dt><dd>{count}</dd>
  </div>)}</dl>;
}
