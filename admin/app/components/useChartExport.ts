'use client';

import { useCallback } from 'react';

/**
 * Hook for exporting chart elements as images
 * Note: Requires html2canvas to be installed for full functionality
 * npm install html2canvas
 */
export function useChartExport() {
  const exportAsImage = useCallback(async (
    elementRef: HTMLElement | null,
    filename: string = 'chart.png'
  ) => {
    if (!elementRef) {
      console.warn('No element reference provided for export');
      return;
    }

    try {
      // Check if html2canvas is available
      if (typeof window !== 'undefined' && 'html2canvas' in window) {
        const html2canvas = (window as any).html2canvas;
        
        const canvas = await html2canvas(elementRef, {
          backgroundColor: '#18181b', // zinc-900
          scale: 2, // Higher quality
        });

        // Convert to blob and download
        canvas.toBlob((blob: Blob | null) => {
          if (!blob) return;
          
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.download = filename;
          link.href = url;
          link.click();
          URL.revokeObjectURL(url);
        });
      } else {
        // Fallback: Copy as text or show message
        console.warn(
          'html2canvas not found. Install it with: npm install html2canvas'
        );
        alert('Export functionality requires html2canvas library. Please install it to enable image export.');
      }
    } catch (error) {
      console.error('Error exporting chart:', error);
      alert('Failed to export chart. Please try again.');
    }
  }, []);

  return { exportAsImage };
}
