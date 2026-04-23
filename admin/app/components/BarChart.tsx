'use client';

import React, { useRef } from 'react';
import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { Chart } from './Chart';

export interface BarChartDataPoint {
  name: string;
  [key: string]: string | number;
}

export interface BarChartProps {
  data: BarChartDataPoint[];
  bars: Array<{
    dataKey: string;
    fill?: string;
    name?: string;
  }>;
  title?: string;
  description?: string;
  xAxisKey?: string;
  className?: string;
  onBarClick?: (data: BarChartDataPoint) => void;
}

const TERMINAL_COLORS = {
  primary: '#00ff00',
  secondary: '#00ffff',
  tertiary: '#ff00ff',
  quaternary: '#ffff00',
  grid: '#333333',
  text: '#a1a1aa',
};

export function BarChart({
  data,
  bars,
  title,
  description,
  xAxisKey = 'name',
  className,
  onBarClick,
}: BarChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);

  const handleExport = () => {
    if (!chartRef.current) return;
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
          <RechartsBarChart
            data={data}
            onClick={(e) => onBarClick && e?.activePayload?.[0] && onBarClick(e.activePayload[0].payload)}
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
              iconType="square"
            />
            {bars.map((bar, index) => {
              const colors = [
                TERMINAL_COLORS.primary,
                TERMINAL_COLORS.secondary,
                TERMINAL_COLORS.tertiary,
                TERMINAL_COLORS.quaternary,
              ];
              return (
                <Bar
                  key={bar.dataKey}
                  dataKey={bar.dataKey}
                  fill={bar.fill || colors[index % colors.length]}
                  name={bar.name || bar.dataKey}
                  cursor={onBarClick ? 'pointer' : 'default'}
                />
              );
            })}
          </RechartsBarChart>
        </ResponsiveContainer>
      </div>
    </Chart>
  );
}
