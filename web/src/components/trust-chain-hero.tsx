'use client';

import { motion } from 'framer-motion';

interface Node {
  id: string;
  x: number;
  y: number;
  label: string;
  score: number;
  delay: number;
}

const nodes: Node[] = [
  { id: 'center', x: 400, y: 250, label: 'isnad', score: 1.0, delay: 0 },
  { id: 'a1', x: 200, y: 150, label: 'Agent A', score: 0.92, delay: 0.3 },
  { id: 'a2', x: 600, y: 150, label: 'Agent B', score: 0.85, delay: 0.5 },
  { id: 'a3', x: 200, y: 350, label: 'Agent C', score: 0.78, delay: 0.7 },
  { id: 'a4', x: 600, y: 350, label: 'Agent D', score: 0.61, delay: 0.9 },
  { id: 'a5', x: 100, y: 250, label: 'Agent E', score: 0.95, delay: 1.1 },
  { id: 'a6', x: 700, y: 250, label: 'Agent F', score: 0.43, delay: 1.3 },
];

const connections = [
  { from: 'center', to: 'a1' },
  { from: 'center', to: 'a2' },
  { from: 'center', to: 'a3' },
  { from: 'center', to: 'a4' },
  { from: 'center', to: 'a5' },
  { from: 'center', to: 'a6' },
  { from: 'a1', to: 'a2' },
  { from: 'a3', to: 'a5' },
  { from: 'a2', to: 'a4' },
];

function getScoreColor(score: number): string {
  if (score >= 0.8) return '#00d4aa';
  if (score >= 0.6) return '#f59e0b';
  return '#ef4444';
}

function getNode(id: string): Node {
  return nodes.find(n => n.id === id)!;
}

export default function TrustChainHero() {
  return (
    <div className="relative w-full max-w-3xl mx-auto aspect-[8/5]">
      {/* Glow effect */}
      <div className="absolute inset-0 bg-gradient-radial from-isnad-teal/10 via-transparent to-transparent opacity-50" />
      
      <svg
        viewBox="0 0 800 500"
        className="w-full h-full"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#00d4aa" stopOpacity="0.2" />
            <stop offset="50%" stopColor="#00d4aa" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#00d4aa" stopOpacity="0.2" />
          </linearGradient>
        </defs>

        {/* Connection lines */}
        {connections.map((conn, i) => {
          const from = getNode(conn.from);
          const to = getNode(conn.to);
          return (
            <motion.line
              key={`line-${i}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke="url(#lineGrad)"
              strokeWidth="1.5"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{ duration: 1.5, delay: 0.5 + i * 0.15, ease: 'easeOut' }}
            />
          );
        })}

        {/* Data flow particles along connections */}
        {connections.map((conn, i) => {
          const from = getNode(conn.from);
          const to = getNode(conn.to);
          return (
            <motion.circle
              key={`particle-${i}`}
              r="3"
              fill="#00d4aa"
              filter="url(#glow)"
              initial={{ cx: from.x, cy: from.y, opacity: 0 }}
              animate={{
                cx: [from.x, to.x],
                cy: [from.y, to.y],
                opacity: [0, 1, 1, 0],
              }}
              transition={{
                duration: 2,
                delay: 2 + i * 0.3,
                repeat: Infinity,
                repeatDelay: 3 + i * 0.5,
                ease: 'easeInOut',
              }}
            />
          );
        })}

        {/* Nodes */}
        {nodes.map((node) => (
          <motion.g
            key={node.id}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.6, delay: node.delay, ease: 'backOut' }}
          >
            {/* Pulse ring */}
            <motion.circle
              cx={node.x}
              cy={node.y}
              r={node.id === 'center' ? 40 : 28}
              fill="none"
              stroke={getScoreColor(node.score)}
              strokeWidth="1"
              initial={{ opacity: 0.5 }}
              animate={{ opacity: [0.5, 0, 0.5], r: node.id === 'center' ? [40, 55, 40] : [28, 40, 28] }}
              transition={{ duration: 3, repeat: Infinity, delay: node.delay }}
            />
            
            {/* Main circle */}
            <circle
              cx={node.x}
              cy={node.y}
              r={node.id === 'center' ? 35 : 24}
              fill={node.id === 'center' ? '#00d4aa' : '#18181b'}
              stroke={getScoreColor(node.score)}
              strokeWidth="2"
              filter="url(#glow)"
            />
            
            {/* Label */}
            <text
              x={node.x}
              y={node.id === 'center' ? node.y + 1 : node.y - 2}
              textAnchor="middle"
              dominantBaseline="middle"
              fill={node.id === 'center' ? '#09090b' : '#fafafa'}
              fontSize={node.id === 'center' ? '14' : '9'}
              fontWeight={node.id === 'center' ? '700' : '500'}
              fontFamily="Inter, sans-serif"
            >
              {node.label}
            </text>
            
            {/* Score */}
            {node.id !== 'center' && (
              <text
                x={node.x}
                y={node.y + 10}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={getScoreColor(node.score)}
                fontSize="8"
                fontWeight="600"
                fontFamily="JetBrains Mono, monospace"
              >
                {node.score.toFixed(2)}
              </text>
            )}
          </motion.g>
        ))}
      </svg>
    </div>
  );
}
