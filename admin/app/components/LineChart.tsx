'use client';

import React, { useRef } from 'react';
import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { Chart } from './Chart';

export interface LineChartDataPoint {
  name: string;
  [key: string]: string | number;
}

export interface LineChartProps {
  data: LineChartDataPoint[];
  lines: Array<{
    dataKey: string;
    stroke?: string;
    name?: string;
  }>;
  title?: string;
  description?: string;
  xAxisKey?: string;
  className?: string;
  onPointClick?: (data: LineChartDataPoint) => void;
}

const TERMINAL_COLORS = {
  primary: '#00ff00',
  secondary: '#00ffff',
  tertiary: '#ff00ff',
  quaternary: '#ffff00',
  grid: '#333333',
  text: '#a1a1aa',
};

export function LineChart({
  data,
  lines,
  title,
  description,
  xAxisKey = 'name',
  className,
  onPointClick,
}: LineChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);

  const handleExport = () => {
    if (!chartRef.current) return;
    
    // Simple export using html2canvas would go here
    // For now, we'll just log
    console.log('Export functionality - integrate html2canvas or similar');
  };

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload) return null;

    return (
      <div className="bg-zinc-950 border border-zinc-700 p-3 rounded shadow-lg">
        <p className="text-xs font-mono text-zinc-400 mb-2">{label}</p>
        {payload.map((entry: any, index: number) => (
          <p key={index} className="text-xs font-mono" style={{ color: entry.color }}>
            {entry.name}: {entry.value}
          </p>
        ))}
      </div>
    );
  };

  return (
    <Chart title={title} description={description} className={className} onExport={handleExport}>
      <div ref={chartRef}>
        <ResponsiveContainer width="100%" height={300}>
          <RechartsLineChart
            data={data}
            onClick={(e) => onPointClick && e?.activePayload?.[0] && onPointClick(e.activePayload[0].payload)}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={TERMINAL_COLORS.grid} />
            <XAxis
              dataKey={xAxisKey}
              stroke={TERMINAL_COLORS.text}
              style={{ fontSize: '11px', fontFamily: 'monospace' }}
            />
            <YAxis
              stroke={TERMINAL_COLORS.text}
              style={{ fontSize: '11px', fontFamily: 'monospace' }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace' }}
              iconType="line"
            />
            {lines.map((line, index) => {
              const colors = [
                TERMINAL_COLORS.primary,
                TERMINAL_COLORS.secondary,
                TERMINAL_COLORS.tertiary,
                TERMINAL_COLORS.quaternary,
              ];
              return (
                <Line
                  key={line.dataKey}
                  type="monotone"
                  dataKey={line.dataKey}
                  stroke={line.stroke || colors[index % colors.length]}
                  name={line.name || line.dataKey}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5, cursor: onPointClick ? 'pointer' : 'default' }}
                />
              );
            })}
          </RechartsLineChart>
        </ResponsiveContainer>
      </div>
    </Chart>
  );
}
