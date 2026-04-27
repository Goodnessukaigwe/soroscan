'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';

export interface TooltipProps {
  /** Content to display in tooltip */
  content: React.ReactNode;
  /** Children element that triggers the tooltip */
  children: React.ReactNode;
  /** Preferred position */
  position?: 'top' | 'bottom' | 'left' | 'right' | 'auto';
  /** Delay before showing tooltip (ms) */
  delay?: number;
  /** Additional CSS classes */
  className?: string;
  /** Disable the tooltip */
  disabled?: boolean;
}

type Position = 'top' | 'bottom' | 'left' | 'right';

const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  position = 'auto',
  delay = 500,
  className = '',
  disabled = false,
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const [actualPosition, setActualPosition] = useState<Position>('top');
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});
  
  const triggerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const timeoutRef = useRef<NodeJS.Timeout | undefined>();

  const calculatePosition = useCallback(() => {
    if (!triggerRef.current || !tooltipRef.current) return;

    const triggerRect = triggerRef.current.getBoundingClientRect();
    const tooltipRect = tooltipRef.current.getBoundingClientRect();
    const viewport = {
      width: window.innerWidth,
      height: window.innerHeight,
    };

    const spacing = 8; // Gap between trigger and tooltip
    const arrowSize = 6;

    // Calculate available space in each direction
    const spaceTop = triggerRect.top;
    const spaceBottom = viewport.height - triggerRect.bottom;
    const spaceLeft = triggerRect.left;
    const spaceRight = viewport.width - triggerRect.right;

    let finalPosition: Position = position === 'auto' ? 'top' : position;

    // Auto-position logic
    if (position === 'auto') {
      if (spaceTop >= tooltipRect.height + spacing) {
        finalPosition = 'top';
      } else if (spaceBottom >= tooltipRect.height + spacing) {
        finalPosition = 'bottom';
      } else if (spaceRight >= tooltipRect.width + spacing) {
        finalPosition = 'right';
      } else if (spaceLeft >= tooltipRect.width + spacing) {
        finalPosition = 'left';
      } else {
        // Fallback to position with most space
        const maxSpace = Math.max(spaceTop, spaceBottom, spaceLeft, spaceRight);
        if (maxSpace === spaceTop) finalPosition = 'top';
        else if (maxSpace === spaceBottom) finalPosition = 'bottom';
        else if (maxSpace === spaceRight) finalPosition = 'right';
        else finalPosition = 'left';
      }
    }

    // Check if preferred position fits, otherwise find best alternative
    const positionFits = {
      top: spaceTop >= tooltipRect.height + spacing,
      bottom: spaceBottom >= tooltipRect.height + spacing,
      left: spaceLeft >= tooltipRect.width + spacing,
      right: spaceRight >= tooltipRect.width + spacing,
    };

    if (!positionFits[finalPosition]) {
      // Find alternative position
      const alternatives: Position[] = ['top', 'bottom', 'left', 'right'];
      finalPosition = alternatives.find(pos => positionFits[pos]) || finalPosition;
    }

    let left = 0;
    let top = 0;

    switch (finalPosition) {
      case 'top':
        left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
        top = triggerRect.top - tooltipRect.height - spacing - arrowSize;
        break;
      case 'bottom':
        left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
        top = triggerRect.bottom + spacing + arrowSize;
        break;
      case 'left':
        left = triggerRect.left - tooltipRect.width - spacing - arrowSize;
        top = triggerRect.top + triggerRect.height / 2 - tooltipRect.height / 2;
        break;
      case 'right':
        left = triggerRect.right + spacing + arrowSize;
        top = triggerRect.top + triggerRect.height / 2 - tooltipRect.height / 2;
        break;
    }

    // Ensure tooltip stays within viewport bounds
    left = Math.max(8, Math.min(left, viewport.width - tooltipRect.width - 8));
    top = Math.max(8, Math.min(top, viewport.height - tooltipRect.height - 8));

    setActualPosition(finalPosition);
    setTooltipStyle({
      position: 'fixed',
      left: `${left}px`,
      top: `${top}px`,
      zIndex: 9999,
    });
  }, [position]);

  const showTooltip = useCallback(() => {
    if (disabled) return;
    
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    
    timeoutRef.current = setTimeout(() => {
      setIsVisible(true);
    }, delay);
  }, [delay, disabled]);

  const hideTooltip = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setIsVisible(false);
  }, []);

  const handleClickOutside = useCallback((event: MouseEvent) => {
    if (
      tooltipRef.current &&
      triggerRef.current &&
      !tooltipRef.current.contains(event.target as Node) &&
      !triggerRef.current.contains(event.target as Node)
    ) {
      hideTooltip();
    }
  }, [hideTooltip]);

  useEffect(() => {
    if (isVisible) {
      calculatePosition();
      document.addEventListener('click', handleClickOutside);
      window.addEventListener('scroll', hideTooltip);
      window.addEventListener('resize', hideTooltip);
    }

    return () => {
      document.removeEventListener('click', handleClickOutside);
      window.removeEventListener('scroll', hideTooltip);
      window.removeEventListener('resize', hideTooltip);
    };
  }, [isVisible, calculatePosition, handleClickOutside, hideTooltip]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const getArrowClasses = () => {
    const baseClasses = 'absolute w-0 h-0 border-solid';
    switch (actualPosition) {
      case 'top':
        return `${baseClasses} border-l-6 border-r-6 border-t-6 border-l-transparent border-r-transparent border-t-gray-900 top-full left-1/2 transform -translate-x-1/2`;
      case 'bottom':
        return `${baseClasses} border-l-6 border-r-6 border-b-6 border-l-transparent border-r-transparent border-b-gray-900 bottom-full left-1/2 transform -translate-x-1/2`;
      case 'left':
        return `${baseClasses} border-t-6 border-b-6 border-l-6 border-t-transparent border-b-transparent border-l-gray-900 left-full top-1/2 transform -translate-y-1/2`;
      case 'right':
        return `${baseClasses} border-t-6 border-b-6 border-r-6 border-t-transparent border-b-transparent border-r-gray-900 right-full top-1/2 transform -translate-y-1/2`;
      default:
        return baseClasses;
    }
  };

  return (
    <>
      <div
        ref={triggerRef}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        className="inline-block"
      >
        {children}
      </div>
      
      {isVisible && (
        <div
          ref={tooltipRef}
          style={tooltipStyle}
          className={`
            bg-gray-900 text-white text-sm px-3 py-2 rounded-lg shadow-lg
            opacity-0 animate-fade-in pointer-events-none
            ${className}
          `}
          role="tooltip"
          aria-hidden={!isVisible}
        >
          <div className={getArrowClasses()} />
          {content}
        </div>
      )}
    </>
  );
};

export default Tooltip;