'use client';

import { motion } from 'framer-motion';

interface RadarChartProps {
  categories: {
    label: string;
    value: number; // 0-1
  }[];
  size?: number;
  color?: string;
}

export default function RadarChart({
  categories,
  size = 300,
  color = '#00d4aa',
}: RadarChartProps) {
  const center = size / 2;
  const maxRadius = (size - 92) / 2;
  const angleStep = (2 * Math.PI) / categories.length;

  function formatLabel(label: string): string[] {
    if (label.length <= 11) return [label];

    const words = label.split(' ');
    if (words.length > 1) {
      const lines: string[] = [];
      let current = '';

      words.forEach((word) => {
        const next = current ? `${current} ${word}` : word;
        if (next.length <= 11) {
          current = next;
          return;
        }

        if (current) lines.push(current);
        current = word;
      });

      if (current) lines.push(current);
      return lines.slice(0, 2).map((line, index) => {
        if (index === 1 && lines.length > 2) return `${line.slice(0, 9)}…`;
        return line;
      });
    }

    return [`${label.slice(0, 10)}…`];
  }

  // Generate polygon points for a given radius multiplier
  function getPolygonPoints(radiusMultiplier: number): string {
    return categories
      .map((_, i) => {
        const angle = angleStep * i - Math.PI / 2;
        const r = maxRadius * radiusMultiplier;
        const x = center + r * Math.cos(angle);
        const y = center + r * Math.sin(angle);
        return `${x},${y}`;
      })
      .join(' ');
  }

  // Data polygon
  const dataPoints = categories.map((cat, i) => {
    const angle = angleStep * i - Math.PI / 2;
    const r = maxRadius * cat.value;
    return { x: center + r * Math.cos(angle), y: center + r * Math.sin(angle) };
  });
  const dataPolygon = dataPoints.map(p => `${p.x},${p.y}`).join(' ');

  // Label positions
  const labelPositions = categories.map((cat, i) => {
    const angle = angleStep * i - Math.PI / 2;
    const r = maxRadius + 20;
    return {
      x: center + r * Math.cos(angle),
      y: center + r * Math.sin(angle),
      angle,
      label: cat.label,
      lines: formatLabel(cat.label),
    };
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="mx-auto">
      {/* Grid rings */}
      {[0.25, 0.5, 0.75, 1.0].map((level) => (
        <polygon
          key={`grid-${level}`}
          points={getPolygonPoints(level)}
          fill="none"
          stroke="#27272a"
          strokeWidth="1"
        />
      ))}

      {/* Axis lines */}
      {categories.map((_, i) => {
        const angle = angleStep * i - Math.PI / 2;
        const x2 = center + maxRadius * Math.cos(angle);
        const y2 = center + maxRadius * Math.sin(angle);
        return (
          <line
            key={`axis-${i}`}
            x1={center}
            y1={center}
            x2={x2}
            y2={y2}
            stroke="#27272a"
            strokeWidth="1"
          />
        );
      })}

      {/* Data polygon */}
      <motion.polygon
        points={dataPolygon}
        fill={`${color}20`}
        stroke={color}
        strokeWidth="2"
        initial={{ opacity: 0, scale: 0.3 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1, ease: 'easeOut', delay: 0.5 }}
        style={{ transformOrigin: `${center}px ${center}px`, filter: `drop-shadow(0 0 8px ${color}30)` }}
      />

      {/* Data points */}
      {dataPoints.map((point, i) => (
        <motion.circle
          key={`point-${i}`}
          cx={point.x}
          cy={point.y}
          r="4"
          fill={color}
          initial={{ opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.8 + i * 0.1 }}
        />
      ))}

      {/* Labels */}
      {labelPositions.map((pos, i) => (
        <text
          key={`label-${i}`}
          x={pos.x}
          y={pos.y}
          textAnchor={
            Math.abs(Math.cos(pos.angle)) < 0.24
              ? 'middle'
              : Math.cos(pos.angle) > 0
                ? 'start'
                : 'end'
          }
          dominantBaseline="middle"
          fill="#a1a1aa"
          fontSize={size < 280 ? '9' : '10'}
          fontFamily="monospace"
        >
          {pos.lines.map((line, index) => (
            <tspan
              key={`${pos.label}-${line}-${index}`}
              x={pos.x}
              dy={index === 0 ? `${(pos.lines.length - 1) * -5}px` : '11px'}
            >
              {line}
            </tspan>
          ))}
        </text>
      ))}
    </svg>
  );
}
