import { useId } from "react";

/** Decorative only: absolute positioning keeps background independent of layout. */
export function StaticBlueWave() {
  const id = useId();
  return (
    <svg
      className="static-blue-wave"
      viewBox="0 0 1440 520"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#d9e7ff" stopOpacity=".6" />
          <stop offset="1" stopColor="#d9e7ff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d="M-60 88C160 12 180 323 462 282S715 340 903 267 1220 188 1490 79V370C1270 241 1180 300 945 349S583 301 420 380 150 145-60 358Z"
        fill={`url(#${id})`}
      />
      {Array.from({ length: 48 }, (_, i) => (
        <path
          key={i}
          d={`M-60 ${178 + i * 2.6} C145 ${50 + i * 2.1} 205 ${388 - i * 1.1} 443 ${291 + i * 0.9} S725 ${358 + i * 0.5} 952 ${280 + i * 1.1} S1250 ${115 + i * 2.8} 1490 ${133 + i * 3.4}`}
          fill="none"
          stroke="#a8c4fb"
          strokeWidth=".65"
          opacity={0.055 + Math.sin((i / 47) * Math.PI) * 0.1}
        />
      ))}
      <path
        d="M-60 344C155 212 205 217 413 374S725 416 969 344 1270 165 1500 306"
        fill="none"
        stroke="#dbe7ff"
        strokeWidth="54"
        opacity=".16"
      />
    </svg>
  );
}

export function HeroBackground() {
  return (
    <div className="hero-background">
      <StaticBlueWave />
    </div>
  );
}
