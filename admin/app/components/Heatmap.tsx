'use client';

import React, { useRef } from 'react';
import { Chart } from './Chart';

export interface HeatmapDataPoint {
  x: string;
  y: string;
  value: number;
}

export interface HeatmapProps {
  data: HeatmapDataPoint[];
  title?: string;
  description?: string;
  className?: string;
  onCellClick?: (data: HeatmapDataPoint) => void;
}

export function Heatmap({
  data,
  title,
  description,
  className,
  onCellClick,
}: HeatmapProps) {
  const chartRef = useRef<HTMLDivElement>(null);

  const handleExport = () => {
    if (!chartRef.current) return;
    console.log('Export functionality - integrate html2canvas or similar');
  };

  // Extract unique x and y values
  const xValues = Array.from(new Set(data.map(d => d.x)));
  const yValues = Array.from(new Set(data.map(d => d.y)));

  // Find min and max values for color scaling
  const values = data.map(d => d.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);

  // Color interpolation function (terminal green gradient)
  const getColor = (value: number): string => {
    if (maxValue === minValue) return '#00ff00';
    
    const normalized = (value - minValue) / (maxValue - minValue);
    
    // Dark green to bright green gradient
    const r = Math.floor(0 * (1 - normalized));
    const g = Math.floor(100 + 155 * normalized);
    const b = Math.floor(0 * (1 - normalized));
    
    return `rgb(${r}, ${g}, ${b})`;
  };

  // Create a map for quick lookup
  const dataMap = new Map<string, number>();
  data.forEach(d => {
    dataMap.set(`${d.x}-${d.y}`, d.value);
  });

  return (
    <Chart title={title} description={description} className={className} onExport={handleExport}>
      <div ref={chartRef} className="overflow-x-auto">
        <div className="inline-block min-w-full">
          <div className="flex">
            {/* Y-axis labels */}
            <div className="flex flex-col justify-around pr-2">
              <div className="h-8" /> {/* Spacer for x-axis labels */}
              {yValues.map((y) => (
                <div
                  key={y}
                  className="text-xs font-mono text-zinc-400 h-8 flex items-center"
                >
                  {y}
                </div>
              ))}
            </div>

            {/* Heatmap grid */}
            <div className="flex-1">
              {/* X-axis labels */}
              <div className="flex mb-1">
                {xValues.map((x) => (
                  <div
                    key={x}
                    className="flex-1 text-xs font-mono text-zinc-400 text-center min-w-[60px]"
                  >
                    {x}
                  </div>
                ))}
              </div>

              {/* Grid cells */}
              {yValues.map((y) => (
                <div key={y} className="flex">
                  {xValues.map((x) => {
                    const value = dataMap.get(`${x}-${y}`) ?? 0;
                    const color = getColor(value);
                    
                    return (
                      <div
                        key={`${x}-${y}`}
                        className="flex-1 h-8 border border-zinc-800 flex items-center justify-center text-xs font-mono cursor-pointer hover:border-zinc-600 transition-colors min-w-[60px]"
                        style={{ backgroundColor: color }}
                        onClick={() => onCellClick && onCellClick({ x, y, value })}
                        title={`${x}, ${y}: ${value}`}
                      >
                        <span className="text-zinc-950 font-bold">{value}</span>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>

          {/* Legend */}
          <div className="mt-4 flex items-center justify-center gap-2">
            <span className="text-xs font-mono text-zinc-400">Low</span>
            <div className="flex h-4 w-48">
              {Array.from({ length: 10 }).map((_, i) => {
                const value = minValue + (maxValue - minValue) * (i / 9);
                return (
                  <div
                    key={i}
                    className="flex-1"
                    style={{ backgroundColor: getColor(value) }}
                  />
                );
              })}
            </div>
            <span className="text-xs font-mono text-zinc-400">High</span>
          </div>
        </div>
      </div>
    </Chart>
  );
}
