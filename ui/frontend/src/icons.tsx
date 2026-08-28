import type { SVGProps } from "react";

export type IconName =
  | "runs"
  | "overview"
  | "queue"
  | "rules"
  | "evidence"
  | "graph"
  | "compare"
  | "regdelta"
  | "diagnostics"
  | "search"
  | "refresh"
  | "menu"
  | "close"
  | "collapse";

const paths: Record<IconName, React.ReactNode> = {
  runs: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  overview: <><path d="m3 11 9-8 9 8" /><path d="M5 10v11h14V10" /><path d="M9 21v-7h6v7" /></>,
  queue: <><path d="M9 5h11M9 12h11M9 19h11" /><path d="m3 5 1 1 2-2M3 12l1 1 2-2M3 19l1 1 2-2" /></>,
  rules: <><path d="M6 3h12l3 3v15H6z" /><path d="M18 3v4h4M9 11h6M9 15h6" /></>,
  evidence: <><path d="M5 3h14v18H5z" /><path d="M8 7h8M8 11h8M8 15h5" /></>,
  graph: <><circle cx="5" cy="12" r="2.5" /><circle cx="18" cy="6" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path d="m7.3 10.9 8.4-3.8M7.3 13.1l8.4 3.8" /></>,
  compare: <><path d="M4 7h14M15 4l3 3-3 3M20 17H6M9 14l-3 3 3 3" /></>,
  regdelta: <><path d="M12 3 4 20h16z" /><path d="M12 9v5" /><circle cx="12" cy="17" r="0.6" fill="currentColor" stroke="none" /></>,
  diagnostics: <><path d="M12 3 2.8 20h18.4z" /><path d="M12 9v5M12 17.5v.1" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m16 16 5 5" /></>,
  refresh: <><path d="M20 7v5h-5" /><path d="M19 12a7 7 0 1 1-2-5" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  collapse: <><path d="M9 18 3 12l6-6M15 6l6 6-6 6" /></>,
};

export function Icon({ name, ...props }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return <svg aria-hidden="true" fill="none" height="20" viewBox="0 0 24 24" width="20" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" {...props}>{paths[name]}</svg>;
}
