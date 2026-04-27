'use client';

import React, { useState, useEffect } from 'react';
import ProgressBar from '../components/ProgressBar';

export default function ProgressDemoPage() {
  const [animatedValue, setAnimatedValue] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setAnimatedValue(prev => (prev >= 100 ? 0 : prev + 1));
    }, 100);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="container mx-auto p-8 space-y-8">
      <h1 className="text-3xl font-bold mb-8">Progress Bar Demo</h1>
      
      {/* Basic Progress Bars */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Basic Progress Bars</h2>
        <ProgressBar value={25} label="25% Complete" />
        <ProgressBar value={50} label="Half Way" variant="success" />
        <ProgressBar value={75} label="Almost Done" variant="warning" />
        <ProgressBar value={90} label="Nearly Finished" variant="danger" />
      </section>

      {/* Label Positions */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Label Positions</h2>
        <ProgressBar value={60} label="Label Above" labelPosition="above" />
        <ProgressBar value={60} label="Label Inside" labelPosition="inside" />
      </section>

      {/* Animated Progress */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Animated Progress</h2>
        <ProgressBar 
          value={animatedValue} 
          label="Auto-incrementing" 
          animated 
          variant="success" 
        />
      </section>

      {/* Indeterminate State */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Indeterminate State</h2>
        <ProgressBar indeterminate label="Loading..." />
        <ProgressBar indeterminate label="Processing" variant="warning" />
      </section>

      {/* Without Percentage */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Without Percentage Display</h2>
        <ProgressBar value={80} label="Custom Progress" showPercentage={false} />
      </section>

      {/* All Variants */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Color Variants</h2>
        <ProgressBar value={70} label="Primary" variant="primary" />
        <ProgressBar value={70} label="Success" variant="success" />
        <ProgressBar value={70} label="Warning" variant="warning" />
        <ProgressBar value={70} label="Danger" variant="danger" />
      </section>
    </div>
  );
}