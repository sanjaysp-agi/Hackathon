// Inline SVG icons (no dependency). Stroke inherits currentColor.

type P = { size?: number };
const base = (size = 16) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export const IcClock = ({ size }: P) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
);
export const IcTrend = ({ size }: P) => (
  <svg {...base(size)}><path d="M3 17l6-6 4 4 7-7" /><path d="M21 8v4h-4" /></svg>
);
export const IcFunnel = ({ size }: P) => (
  <svg {...base(size)}><path d="M3 4h18l-7 8v6l-4 2v-8L3 4z" /></svg>
);
export const IcUsers = ({ size }: P) => (
  <svg {...base(size)}><circle cx="9" cy="8" r="3" /><path d="M3 20c0-3 3-5 6-5s6 2 6 5" /><path d="M16 6a3 3 0 010 6M18 20c0-2-1-3.5-2.5-4.5" /></svg>
);
export const IcPause = ({ size }: P) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="9" /><path d="M10 9v6M14 9v6" /></svg>
);
export const IcPulse = ({ size }: P) => (
  <svg {...base(size)}><path d="M3 12h4l2-5 4 10 2-5h6" /></svg>
);
export const IcAlert = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 3l9 16H3l9-16z" /><path d="M12 10v4M12 17.5v.5" /></svg>
);
export const IcCheck = ({ size }: P) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="9" /><path d="M8.5 12.5l2.5 2.5 4.5-5" /></svg>
);
export const IcDot = ({ size }: P) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" /></svg>
);
export const IcArrow = ({ size }: P) => (
  <svg {...base(size)}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const IcSpark = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" /></svg>
);
export const IcTool = ({ size }: P) => (
  <svg {...base(size)}><path d="M14 7a3 3 0 00-4 4L4 17l3 3 6-6a3 3 0 004-4l-2 2-2-2 1-3z" /></svg>
);
export const IcSun = ({ size }: P) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19" /></svg>
);
export const IcMoon = ({ size }: P) => (
  <svg {...base(size)}><path d="M20 14a8 8 0 01-10-10 8 8 0 1010 10z" /></svg>
);
export const IcGrid = ({ size }: P) => (
  <svg {...base(size)}><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></svg>
);
export const IcShield = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6l7-3z" /><path d="M9 12l2 2 4-4" /></svg>
);
export const IcClose = ({ size }: P) => (
  <svg {...base(size)}><path d="M6 6l12 12M18 6L6 18" /></svg>
);
export const IcChat = ({ size }: P) => (
  <svg {...base(size)}><path d="M4 5h16v11H9l-4 3v-3H4z" /><path d="M8 10h8M8 13h5" /></svg>
);
export const IcBack = ({ size }: P) => (
  <svg {...base(size)}><path d="M19 12H5M11 6l-6 6 6 6" /></svg>
);
export const IcInfo = ({ size }: P) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8v.5" /></svg>
);
export const IcChevron = ({ size }: P) => (
  <svg {...base(size)}><path d="M6 9l6 6 6-6" /></svg>
);
export const IcLayers = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 3l9 5-9 5-9-5 9-5z" /><path d="M3 13l9 5 9-5" /></svg>
);
export const IcReset = ({ size }: P) => (
  <svg {...base(size)}><path d="M3 12a9 9 0 109-9 9 9 0 00-7 3.3" /><path d="M4 3v4h4" /></svg>
);
