'use client';

import React from 'react';

export interface ProgressBarProps {
  /** Progress value from 0 to 100 */
  value?: number;
  /** Color variant */
  variant?: 'success' | 'warning' | 'danger' | 'primary';
  /** Label text */
  label?: string;
  /** Label position */
  labelPosition?: 'above' | 'inside';
  /** Show animated fill */
  animated?: boolean;
  /** Indeterminate state (ignores value) */
  indeterminate?: boolean;
  /** Additional CSS classes */
  className?: string;
  /** Show percentage text */
  showPercentage?: boolean;
}

const ProgressBar: React.FC<ProgressBarProps> = ({
  value = 0,
  variant = 'primary',
  label,
  labelPosition = 'above',
  animated = false,
  indeterminate = false,
  className = '',
  showPercentage = true,
}) => {
  // Clamp value between 0 and 100
  const clampedValue = Math.max(0, Math.min(100, value));
  
  const variantClasses = {
    primary: 'bg-blue-500',
    success: 'bg-green-500',
    warning: 'bg-yellow-500',
    danger: 'bg-red-500',
  };

  const backgroundClasses = {
    primary: 'bg-blue-100',
    success: 'bg-green-100',
    warning: 'bg-yellow-100',
    danger: 'bg-red-100',
  };

  return (
    <div className={`w-full ${className}`}>
      {/* Label above */}
      {label && labelPosition === 'above' && (
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium text-gray-700">{label}</span>
          {showPercentage && !indeterminate && (
            <span className="text-sm text-gray-500">{clampedValue}%</span>
          )}
        </div>
      )}
      
      {/* Progress bar container */}
      <div 
        className={`relative w-full h-4 rounded-full overflow-hidden ${backgroundClasses[variant]}`}
        role="progressbar"
        aria-valuenow={indeterminate ? undefined : clampedValue}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label || `Progress: ${clampedValue}%`}
      >
        {/* Progress fill */}
        <div
          className={`
            h-full rounded-full transition-all duration-300 ease-out
            ${variantClasses[variant]}
            ${animated ? 'animate-pulse' : ''}
            ${indeterminate ? 'animate-indeterminate' : ''}
          `}
          style={{
            width: indeterminate ? '100%' : `${clampedValue}%`,
            transform: indeterminate ? 'translateX(-100%)' : 'translateX(0)',
          }}
        />
        
        {/* Label inside */}
        {label && labelPosition === 'inside' && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xs font-medium text-white mix-blend-difference">
              {label}
              {showPercentage && !indeterminate && ` ${clampedValue}%`}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default ProgressBar;