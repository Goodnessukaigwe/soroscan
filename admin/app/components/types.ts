/**
 * Shared types for chart components
 */

export interface BaseChartProps {
  title?: string;
  description?: string;
  className?: string;
}

export interface InteractiveChartProps<T> extends BaseChartProps {
  data: T[];
  onExport?: () => void;
}

export type ChartColor = string;

export interface ChartTheme {
  primary: ChartColor;
  secondary: ChartColor;
  tertiary: ChartColor;
  quaternary: ChartColor;
  grid: ChartColor;
  text: ChartColor;
  background: ChartColor;
  border: ChartColor;
}

export const TERMINAL_THEME: ChartTheme = {
  primary: '#00ff00',    // green
  secondary: '#00ffff',  // cyan
  tertiary: '#ff00ff',   // magenta
  quaternary: '#ffff00', // yellow
  grid: '#333333',       // dark gray
  text: '#a1a1aa',       // zinc-400
  background: '#18181b', // zinc-900
  border: '#27272a',     // zinc-800
};
