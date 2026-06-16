import { cn } from "@/lib/utils";

export interface RiskScoreGaugeProps {
  score: number; // 0-100
  size?: number; // px diameter
  className?: string;
}

function riskBand(score: number): { label: string; color: string } {
  if (score < 30) return { label: "Low Risk", color: "hsl(142 71% 45%)" };
  if (score <= 60) return { label: "Medium Risk", color: "hsl(38 92% 50%)" };
  return { label: "High Risk", color: "hsl(0 72% 51%)" };
}

export function RiskScoreGauge({
  score,
  size = 140,
  className,
}: RiskScoreGaugeProps) {
  const clamped = Math.max(0, Math.min(100, score));
  const { label, color } = riskBand(clamped);

  const strokeWidth = size * 0.09;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped / 100);
  const center = size / 2;

  return (
    <div
      className={cn("inline-flex flex-col items-center", className)}
      role="img"
      aria-label={`Risk score ${Math.round(clamped)} out of 100, ${label}`}
    >
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            strokeWidth={strokeWidth}
            className="stroke-muted"
          />
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            strokeWidth={strokeWidth}
            stroke={color}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset 0.6s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold tabular-nums">
            {Math.round(clamped)}
          </span>
          <span className="text-xs text-muted-foreground">/ 100</span>
        </div>
      </div>
      <span className="mt-2 text-sm font-medium" style={{ color }}>
        {label}
      </span>
    </div>
  );
}
