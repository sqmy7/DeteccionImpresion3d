import type { ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";

/** Plain table primitives with the app's look; wraps in a horizontal scroller for small screens. */
export function Table({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  );
}

export function Th({ children, className = "", ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={`whitespace-nowrap border-b border-line px-3 py-2 text-xs font-medium uppercase tracking-wide text-faint ${className}`}
      {...props}
    >
      {children}
    </th>
  );
}

export function Td({ children, className = "", ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={`border-b border-line/60 px-3 py-2 align-top text-fg ${className}`} {...props}>
      {children}
    </td>
  );
}
