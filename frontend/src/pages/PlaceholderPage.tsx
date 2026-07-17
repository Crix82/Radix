import { PageHead } from "../components/Layout";

// Temporary body for screens whose real implementation arrives in a later milestone.
export function PlaceholderPage({
  title,
  subtitle,
  note,
}: {
  title: string;
  subtitle: string;
  note: string;
}) {
  return (
    <>
      <PageHead title={title} subtitle={subtitle} />
      <div className="card px-5 py-10 text-center text-[13px] text-ink3">{note}</div>
    </>
  );
}
