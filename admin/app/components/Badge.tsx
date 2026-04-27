'use client';

import React from 'react';

export interface BadgeProps {
  /** Text content of the badge */
  label: string;
  /** Color variant */
  variant?: 'success' | 'error' | 'warning' | 'info';
  /** Size variant */
  size?: 'compact' | 'normal';
  /** Shape option */
  shape?: 'rounded' | 'square';
  /** Optional icon rendered before the label */
  icon?: React.ReactNode;
  /** Whether the badge can be dismissed */
  dismissible?: boolean;
  /** Callback when dismissed */
  onDismiss?: () => void;
  /** Additional CSS classes */
  className?: string;
}

const variantClasses: Record<NonNullable<BadgeProps['variant']>, string> = {
  success: 'bg-green-100 text-green-800 border border-green-200',
  error:   'bg-red-100 text-red-800 border border-red-200',
  warning: 'bg-yellow-100 text-yellow-800 border border-yellow-200',
  info:    'bg-blue-100 text-blue-800 border border-blue-200',
};

const dismissHoverClasses: Record<NonNullable<BadgeProps['variant']>, string> = {
  success: 'hover:bg-green-200',
  error:   'hover:bg-red-200',
  warning: 'hover:bg-yellow-200',
  info:    'hover:bg-blue-200',
};

const sizeClasses: Record<NonNullable<BadgeProps['size']>, string> = {
  compact: 'px-1.5 py-0.5 text-xs gap-1',
  normal:  'px-2.5 py-1 text-sm gap-1.5',
};

const shapeClasses: Record<NonNullable<BadgeProps['shape']>, string> = {
  rounded: 'rounded-full',
  square:  'rounded',
};

const Badge: React.FC<BadgeProps> = ({
  label,
  variant = 'info',
  size = 'normal',
  shape = 'rounded',
  icon,
  dismissible = false,
  onDismiss,
  className = '',
}) => {
  return (
    <span
      className={`
        inline-flex items-center font-medium
        ${variantClasses[variant]}
        ${sizeClasses[size]}
        ${shapeClasses[shape]}
        ${className}
      `.trim().replace(/\s+/g, ' ')}
      role="status"
      aria-label={label}
    >
      {icon && (
        <span className="inline-flex shrink-0" aria-hidden="true">
          {icon}
        </span>
      )}

      <span>{label}</span>

      {dismissible && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={`Dismiss ${label}`}
          className={`
            inline-flex items-center justify-center shrink-0 rounded-full
            -mr-0.5 ml-0.5 w-4 h-4
            transition-colors
            ${dismissHoverClasses[variant]}
          `.trim().replace(/\s+/g, ' ')}
        >
          <svg
            viewBox="0 0 8 8"
            fill="currentColor"
            className="w-2.5 h-2.5"
            aria-hidden="true"
          >
            <path d="M1.5 1.5l5 5M6.5 1.5l-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      )}
    </span>
  );
};

export default Badge;
