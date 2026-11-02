import Link from "next/link";
import { EmptyState } from "@/components/ui/card";

export default function NotFound() {
  return (
    <EmptyState title="Not found">
      That page does not exist (or the data for it has not been published). <Link href="/" className="underline">Back to this week&apos;s fixtures</Link>.
    </EmptyState>
  );
}
