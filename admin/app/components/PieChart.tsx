'use client';

import React, { useRef, useState } from 'react';
import {
  PieChart as RechartsPieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { Chart } from './Chart';

export interface PieChartDataPoint {
  name: string;
  value: number;
}

export interface PieChartProps {
  data: PieChartDataPoint[];
  title?: string;
  description?: string;
  className?: string;
  onSliceClick?: (data: PieChartDataPoint) => void;
}

const TERMINAL_COLORS = [
  '#00ff00', // green
  '#00ffff', // cyan
  '#ff00ff', // magenta
  '#ffff00', // yellow
  '#ff8800', // orange
  '#8800ff', // purple
  '#00ff88', // teal
  '#ff0088', // pink
];

export function PieChart({
  data,
  title,
  description,
  className,
  onSliceClick,
}: PieChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const handleExport = () => {
    if (!chartRef.current) return;
    console.log('Export functionality - integrate html2canvas or similar');
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload || !payload[0]) return null;

    const data = payload[0];
    const total = payload[0].payload.payload?.total || 0;
    const percentage = total > 0 ? ((data.value / total) * 100).toFixed(1) : 0;

    return (
      <div className="bg-zinc-950 border border-zinc-700 p-3 rounded shadow-lg">
        <p className="text-xs font-mono text-zinc-400 mb-1">{data.name}</p>
        <p className="text-xs font-mono" style={{ color: data.payload.fill }}>
          Value: {data.value}
        </p>
        <p className="text-xs font-mono text-zinc-500">
          {percentage}%
        </p>
      </div>
    );
  };

  const onPieEnter = (_: any, index: number) => {
    setActiveIndex(index);
  };

  const onPieLeave = () => {
    setActiveIndex(null);
  };

  // Calculate total for percentage display
  const total = data.reduce((sum, item) => sum + item.value, 0);
  const dataWithTotal = data.map(item => ({ ...item, total }));

  return (
    <Chart title={title} description={description} className={className} onExport={handleExport}>
      <div ref={chartRef}>
        <ResponsiveContainer width="100%" height={300}>
          <RechartsPieChart>
            <Pie
              data={dataWithTotal}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
              outerRadius={80}
              fill="#8884d8"
              dataKey="value"
              onMouseEnter={onPieEnter}
              onMouseLeave={onPieLeave}
              onClick={(data) => onSliceClick && onSliceClick(data)}
              cursor={onSliceClick ? 'pointer' : 'default'}
            >
              {data.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={TERMINAL_COLORS[index % TERMINAL_COLORS.length]}
                  opacity={activeIndex === null || activeIndex === index ? 1 : 0.6}
                  style={{
                    fontSize: '10px',
                    fontFamily: 'monospace',
                    fill: '#a1a1aa',
                  }}
                />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace' }}
              iconType="circle"
            />
          </RechartsPieChart>
        </ResponsiveContainer>
      </div>
    </Chart>
  );
}
