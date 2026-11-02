import clsx from "clsx";
import type { ReactNode } from "react";

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className="-mx-4 overflow-x-auto sm:mx-0">
      <table className={clsx("w-full min-w-max border-collapse text-sm tabular", className)}>{children}</table>
    </div>
  );
}

export function Th({ children, className, title }: { children?: ReactNode; className?: string; title?: string }) {
  return (
    <th title={title} className={clsx("border-b border-border px-2 py-2 text-left text-xs font-medium text-fg-3 first:pl-4 sm:first:pl-2", className)}>
      {children}
    </th>
  );
}

export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={clsx("border-b border-border/60 px-2 py-1.5 first:pl-4 sm:first:pl-2", className)}>{children}</td>;
}
