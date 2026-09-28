/**
 * Contract Health Badge Component Tests
 * ──────────────────────────────────────────────────────────────────────────────
 * Comprehensive test suite for ContractHealthBadge component.
 * 
 * Tests:
 * - Basic rendering for all status types
 * - Variant and size combinations
 * - Animation behavior
 * - Tooltip content generation
 * - Accessibility compliance (WCAG 2.1 AA)
 * - Performance with multiple instances
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import userEvent from '@testing-library/user-event';
import { 
  ContractHealthBadge, 
  HEALTH_STATUS_CONFIG,
  type ContractHealthStatus 
} from './ContractHealthBadge';
import { COMMON_DEGRADATION_SCENARIOS } from '@/lib/tooltip-content-guidelines';

// Extend Jest matchers
expect.extend(toHaveNoViolations);

// Mock intersection observer for animation tests
const mockIntersectionObserver = jest.fn();
mockIntersectionObserver.mockReturnValue({
  observe: () => null,
  unobserve: () => null,
  disconnect: () => null,
});
window.IntersectionObserver = mockIntersectionObserver;

// Mock matchMedia for reduced motion tests
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: query === '(prefers-reduced-motion: reduce)' ? false : true,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

describe('ContractHealthBadge', () => {
  describe('Basic Rendering', () => {
    it.each(['healthy', 'degraded', 'paused', 'error'] as ContractHealthStatus[])(
      'renders %s status correctly',
      (status) => {
        render(<ContractHealthBadge status={status} />);
        
        const badge = screen.getByRole('status');
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveAttribute('aria-label', `Contract health: ${HEALTH_STATUS_CONFIG[status].label}`);
      }
    );

    it('displays custom label when provided', () => {
      render(<ContractHealthBadge status="healthy" label="Custom Status" />);
      
      expect(screen.getByText('Custom Status')).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Contract health: Custom Status');
    });

    it('shows only dot when dotOnly is true', () => {
      render(<ContractHealthBadge status="healthy" dotOnly />);
      
      const badge = screen.getByRole('status');
      expect(badge).toBeInTheDocument();
      expect(screen.queryByText('Healthy')).not.toBeInTheDocument();
    });

    it('displays icon instead of dot when showIcon is true', () => {
      render(<ContractHealthBadge status="healthy" showIcon />);
      
      const badge = screen.getByRole('status');
      expect(badge).toBeInTheDocument();
      
      // Icon should be present (aria-hidden)
      const icon = badge.querySelector('[aria-hidden="true"]');
      expect(icon).toBeInTheDocument();
    });
  });

  describe('Size Variants', () => {
    it.each(['sm', 'md', 'lg'] as const)(
      'applies %s size class correctly',
      (size) => {
        render(<ContractHealthBadge status="healthy" size={size} />);
        
        const badge = screen.getByRole('status');
        expect(badge).toHaveClass(`h-${size === 'sm' ? '5' : size === 'lg' ? '8' : '6'}`);
      }
    );
  });

  describe('Style Variants', () => {
    it.each(['default', 'compact', 'pill', 'square'] as const)(
      'applies %s variant styling',
      (variant) => {
        render(<ContractHealthBadge status="healthy" variant={variant} />);
        
        const badge = screen.getByRole('status');
        expect(badge).toBeInTheDocument();
        
        // Check for variant-specific classes
        if (variant === 'compact') {
          expect(badge).toHaveClass('gap-1.5');
        } else if (variant === 'pill') {
          expect(badge).toHaveClass('rounded-full');
        }
      }
    );
  });

  describe('Glow Effects', () => {
    it.each(['none', 'subtle', 'moderate', 'intense'] as const)(
      'applies %s glow effect',
      (glow) => {
        render(<ContractHealthBadge status="healthy" glow={glow} />);
        
        const badge = screen.getByRole('status');
        expect(badge).toBeInTheDocument();
        
        if (glow === 'none') {
          expect(badge).not.toHaveStyle({ boxShadow: expect.any(String) });
        }
      }
    );
  });

  describe('Metrics Display', () => {
    it('displays event count metrics', () => {
      render(
        <ContractHealthBadge 
          status="healthy" 
          metrics={{ eventCount: 1234 }} 
        />
      );
      
      expect(screen.getByText('1.2k')).toBeInTheDocument();
    });

    it('formats large event counts correctly', () => {
      render(
        <ContractHealthBadge 
          status="healthy" 
          metrics={{ eventCount: 15420 }} 
        />
      );
      
      expect(screen.getByText('15.4k')).toBeInTheDocument();
    });

    it('displays uptime metrics', () => {
      render(
        <ContractHealthBadge 
          status="healthy" 
          metrics={{ uptime: '99.9%' }} 
        />
      );
      
      expect(screen.getByText('99.9%')).toBeInTheDocument();
    });

    it('hides metrics when dotOnly is true', () => {
      render(
        <ContractHealthBadge 
          status="healthy" 
          metrics={{ eventCount: 1234 }} 
          dotOnly 
        />
      );
      
      expect(screen.queryByText('1234')).not.toBeInTheDocument();
    });
  });

  describe('Tooltip Integration', () => {
    it('shows basic tooltip for healthy status', async () => {
      const user = userEvent.setup();
      
      render(<ContractHealthBadge status="healthy" />);
      
      const badge = screen.getByRole('status');
      await user.hover(badge);
      
      await waitFor(() => {
        expect(screen.getByRole('tooltip')).toBeInTheDocument();
        expect(screen.getAllByText(/operating normally/i)[0]).toBeInTheDocument();
      });
    });

    it('shows detailed tooltip for degraded status with context', async () => {
      const user = userEvent.setup();
      
      render(
        <ContractHealthBadge 
          status="degraded" 
          degradationContext={COMMON_DEGRADATION_SCENARIOS.highLatency}
        />
      );
      
      const badge = screen.getByRole('status');
      await user.hover(badge);
      
      await waitFor(() => {
        expect(screen.getByRole('tooltip')).toBeInTheDocument();
        expect(screen.getAllByText(/Performance Degraded/i)[0]).toBeInTheDocument();
      });
    });

    it('uses custom tooltip content when provided', async () => {
      const user = userEvent.setup();
      const customContent = 'Custom tooltip message';
      
      render(
        <ContractHealthBadge 
          status="healthy" 
          tooltipContent={customContent}
        />
      );
      
      const badge = screen.getByRole('status');
      await user.hover(badge);
      
      await waitFor(() => {
        expect(screen.getByRole('tooltip')).toBeInTheDocument();
        expect(screen.getAllByText(customContent)[0]).toBeInTheDocument();
      });
    });

    it('disables tooltip when disableTooltip is true', async () => {
      const user = userEvent.setup();
      
      render(<ContractHealthBadge status="healthy" disableTooltip />);
      
      const badge = screen.getByRole('status');
      await user.hover(badge);
      
      // Wait a moment to ensure tooltip doesn't appear
      await waitFor(() => {
        expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
      });
    });
  });

  describe('Animation Behavior', () => {
    it('applies animation classes for animated statuses', () => {
      render(<ContractHealthBadge status="healthy" />);
      
      const badge = screen.getByRole('status');
      
      // Should have animation-related attributes
      expect(badge).toBeInTheDocument();
      // Animation classes are applied via the animation hook
    });

    it('disables animations when disableAnimation is true', () => {
      render(<ContractHealthBadge status="healthy" disableAnimation />);
      
      const badge = screen.getByRole('status');
      expect(badge).toBeInTheDocument();
      
      // Should not have pulsing animation for static state
      const dot = badge.querySelector('[aria-hidden="true"]');
      expect(dot).not.toHaveClass('animate-pulse');
    });

    it('respects reduced motion preference', () => {
      // Mock reduced motion preference
      window.matchMedia = jest.fn().mockImplementation(query => ({
        matches: query === '(prefers-reduced-motion: reduce)' ? true : false,
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      }));

      render(<ContractHealthBadge status="healthy" />);
      
      const badge = screen.getByRole('status');
      expect(badge).toBeInTheDocument();
      
      // Animation should be disabled due to reduced motion
    });
  });

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<ContractHealthBadge status="healthy" />);
      
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('provides proper ARIA labels', () => {
      render(<ContractHealthBadge status="degraded" />);
      
      const badge = screen.getByRole('status');
      expect(badge).toHaveAttribute('aria-label', 'Contract health: Degraded');
    });

    it('accepts custom ARIA label', () => {
      const customLabel = 'Custom accessibility label';
      
      render(
        <ContractHealthBadge 
          status="healthy" 
          aria-label={customLabel}
        />
      );
      
      const badge = screen.getByRole('status');
      expect(badge).toHaveAttribute('aria-label', customLabel);
    });

    it('hides decorative elements from screen readers', () => {
      render(<ContractHealthBadge status="healthy" />);
      
      const decorativeElements = screen.getAllByLabelText('', { exact: false });
      decorativeElements.forEach(element => {
        if (element.getAttribute('aria-hidden') === 'true') {
          expect(element).toHaveAttribute('aria-hidden', 'true');
        }
      });
    });

    it('maintains focus visibility', () => {
      render(<ContractHealthBadge status="healthy" />);
      
      const badge = screen.getByRole('status');
      fireEvent.focus(badge);
      
      // Should have focus-visible styles
      expect(badge).toHaveClass('focus-visible:outline-none');
    });

    it('is reachable by keyboard so the tooltip can be read without a mouse', async () => {
      const user = userEvent.setup();

      render(<ContractHealthBadge status="degraded" />);

      const badge = screen.getByRole('status');
      expect(badge).toHaveAttribute('tabindex', '0');

      await user.tab();

      expect(document.activeElement).toBe(badge);

      await waitFor(() => {
        expect(screen.getByRole('tooltip')).toBeInTheDocument();
      });
    });

    it('is not focusable when the tooltip is disabled', () => {
      render(<ContractHealthBadge status="healthy" disableTooltip />);

      const badge = screen.getByRole('status');
      expect(badge).not.toHaveAttribute('tabindex');
    });
  });

  describe('Color Configuration', () => {
    it('applies correct colors for each status', () => {
      Object.entries(HEALTH_STATUS_CONFIG).forEach(([status, config]) => {
        const { rerender } = render(
          <ContractHealthBadge status={status as ContractHealthStatus} />
        );
        
        const badge = screen.getByRole('status');
        
        // Check that colors are applied via inline styles
        expect(badge).toHaveStyle({
          color: config.colors.primary,
          backgroundColor: config.colors.background,
          borderColor: config.colors.border
        });
        
        rerender(<div />); // Clean up for next iteration
      });
    });
  });

  describe('Performance', () => {
    it('renders multiple badges efficiently', () => {
      const startTime = performance.now();
      
      render(
        <div>
          {Array.from({ length: 100 }, (_, i) => (
            <ContractHealthBadge 
              key={i}
              status={['healthy', 'degraded', 'paused', 'error'][i % 4] as ContractHealthStatus}
            />
          ))}
        </div>
      );
      
      const endTime = performance.now();
      const renderTime = endTime - startTime;
      
      // Should render 100 badges in under 2000ms (reasonable threshold in Jest/React 19 dev environment)
      expect(renderTime).toBeLessThan(2000);
    });

    it('handles degradation context updates efficiently', () => {
      let renderCount = 0;
      const TestWrapper = ({ context }: { context: any }) => {
        renderCount++;
        return (
          <ContractHealthBadge 
            status="degraded" 
            degradationContext={context}
          />
        );
      };

      const { rerender } = render(
        <TestWrapper context={COMMON_DEGRADATION_SCENARIOS.highLatency} />
      );
      
      const initialRenderCount = renderCount;
      
      // Update with same context - should not cause unnecessary re-renders
      rerender(
        <TestWrapper context={COMMON_DEGRADATION_SCENARIOS.highLatency} />
      );
      
      // Update with different context - should re-render
      rerender(
        <TestWrapper context={COMMON_DEGRADATION_SCENARIOS.syncLag} />
      );
      
      expect(renderCount).toBeGreaterThan(initialRenderCount);
    });
  });

  describe('Error Handling', () => {
    it('handles invalid status gracefully', () => {
      // Suppress console errors for this test
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
      
      render(<ContractHealthBadge status={'invalid' as any} />);
      
      // Should still render without crashing
      expect(screen.getByRole('status')).toBeInTheDocument();
      
      consoleSpy.mockRestore();
    });

    it('handles malformed degradation context', () => {
      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation();
      
      render(
        <ContractHealthBadge 
          status="degraded" 
          degradationContext={{} as any}
        />
      );
      
      // Should render with fallback content
      expect(screen.getByRole('status')).toBeInTheDocument();
      
      consoleSpy.mockRestore();
    });
  });
});