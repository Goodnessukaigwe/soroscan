import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import ProgressBar from '../ProgressBar';

describe('ProgressBar', () => {
  it('renders with default props', () => {
    render(<ProgressBar />);
    const progressBar = screen.getByRole('progressbar');
    expect(progressBar).toBeInTheDocument();
    expect(progressBar).toHaveAttribute('aria-valuenow', '0');
  });

  it('displays correct percentage value', () => {
    render(<ProgressBar value={75} />);
    const progressBar = screen.getByRole('progressbar');
    expect(progressBar).toHaveAttribute('aria-valuenow', '75');
    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  it('clamps values between 0 and 100', () => {
    const { rerender } = render(<ProgressBar value={150} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
    
    rerender(<ProgressBar value={-10} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  });

  it('renders label above progress bar', () => {
    render(<ProgressBar label="Loading..." labelPosition="above" value={50} />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('renders label inside progress bar', () => {
    render(<ProgressBar label="Processing" labelPosition="inside" value={30} />);
    expect(screen.getByText('Processing 30%')).toBeInTheDocument();
  });

  it('applies correct variant classes', () => {
    const { container } = render(<ProgressBar variant="success" value={50} />);
    const progressFill = container.querySelector('.bg-green-500');
    expect(progressFill).toBeInTheDocument();
  });

  it('handles indeterminate state', () => {
    render(<ProgressBar indeterminate />);
    const progressBar = screen.getByRole('progressbar');
    expect(progressBar).not.toHaveAttribute('aria-valuenow');
  });

  it('hides percentage in indeterminate state', () => {
    render(<ProgressBar indeterminate value={50} />);
    expect(screen.queryByText('50%')).not.toBeInTheDocument();
  });

  it('can hide percentage display', () => {
    render(<ProgressBar value={75} showPercentage={false} />);
    expect(screen.queryByText('75%')).not.toBeInTheDocument();
  });

  it('applies custom className', () => {
    const { container } = render(<ProgressBar className="custom-class" />);
    expect(container.firstChild).toHaveClass('custom-class');
  });

  it('has proper accessibility attributes', () => {
    render(<ProgressBar value={60} label="File upload" />);
    const progressBar = screen.getByRole('progressbar');
    expect(progressBar).toHaveAttribute('aria-valuemin', '0');
    expect(progressBar).toHaveAttribute('aria-valuemax', '100');
    expect(progressBar).toHaveAttribute('aria-label', 'File upload');
  });
});