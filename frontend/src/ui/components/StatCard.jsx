import React from 'react';
import { cn } from '@/lib/utils';

export default function StatCard({ label, value, hint, className, accent }) {
  return (
    <div className={cn('stat-card', accent && `stat-card-${accent}`, className)}>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}
