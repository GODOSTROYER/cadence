import { Link, useLocation } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { PageTransition } from "@/components/PageTransition";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

export default function NotFound() {
  useDocumentTitle("Not found");
  const { pathname } = useLocation();
  return (
    <PageTransition>
      <PageHeader eyebrow="404" title="No such page" description={<>Nothing lives at <code className="t-mono text-text">{pathname}</code>.</>} />
      <Link to="/" className="btn btn-primary">
        Back to the overview
      </Link>
    </PageTransition>
  );
}
