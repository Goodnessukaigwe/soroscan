import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import Badge from '../Badge';

describe('Badge', () => {
  // --- Rendering ---
  it('renders with required label', () => {
    render(<Badge label="Active" />);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('has role="status"', () => {
    render(<Badge label="Active" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  // --- Variant colours ---
  it('applies success variant classes', () => {
    const { container } = render(<Badge label="OK" variant="success" />);
    expect(container.firstChild).toHaveClass('bg-green-100', 'text-green-800');
  });

  it('applies error variant classes', () => {
    const { container } = render(<Badge label="Fail" variant="error" />);
    expect(container.firstChild).toHaveClass('bg-red-100', 'text-red-800');
  });

  it('applies warning variant classes', () => {
    const { container } = render(<Badge label="Warn" variant="warning" />);
    expect(container.firstChild).toHaveClass('bg-yellow-100', 'text-yellow-800');
  });

  it('applies info variant classes (default)', () => {
    const { container } = render(<Badge label="Info" />);
    expect(container.firstChild).toHaveClass('bg-blue-100', 'text-blue-800');
  });

  // --- Size variants ---
  it('applies normal size classes by default', () => {
    const { container } = render(<Badge label="Normal" />);
    expect(container.firstChild).toHaveClass('px-2.5', 'py-1', 'text-sm');
  });

  it('applies compact size classes', () => {
    const { container } = render(<Badge label="Small" size="compact" />);
    expect(container.firstChild).toHaveClass('px-1.5', 'py-0.5', 'text-xs');
  });

  // --- Shape variants ---
  it('applies rounded shape by default', () => {
    const { container } = render(<Badge label="Pill" />);
    expect(container.firstChild).toHaveClass('rounded-full');
  });

  it('applies square shape', () => {
    const { container } = render(<Badge label="Square" shape="square" />);
    expect(container.firstChild).toHaveClass('rounded');
    expect(container.firstChild).not.toHaveClass('rounded-full');
  });

  // --- Icon support ---
  it('renders icon when provided', () => {
    render(<Badge label="With Icon" icon={<svg data-testid="test-icon" />} />);
    expect(screen.getByTestId('test-icon')).toBeInTheDocument();
  });

  it('renders without icon when not provided', () => {
    render(<Badge label="No Icon" />);
    expect(screen.queryByTestId('test-icon')).not.toBeInTheDocument();
  });

  // --- Dismissible ---
  it('renders dismiss button when dismissible=true', () => {
    render(<Badge label="Close me" dismissible />);
    expect(screen.getByRole('button', { name: /dismiss close me/i })).toBeInTheDocument();
  });

  it('does not render dismiss button by default', () => {
    render(<Badge label="Static" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('calls onDismiss when dismiss button is clicked', () => {
    const handleDismiss = jest.fn();
    render(<Badge label="Bye" dismissible onDismiss={handleDismiss} />);
    fireEvent.click(screen.getByRole('button', { name: /dismiss bye/i }));
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('dismiss button is accessible with aria-label', () => {
    render(<Badge label="Tag" dismissible />);
    const btn = screen.getByRole('button');
    expect(btn).toHaveAttribute('aria-label', 'Dismiss Tag');
  });

  // --- Custom className ---
  it('applies custom className', () => {
    const { container } = render(<Badge label="Custom" className="my-custom-class" />);
    expect(container.firstChild).toHaveClass('my-custom-class');
  });
});
