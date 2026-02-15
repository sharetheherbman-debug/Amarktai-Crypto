import React from 'react';
import { cn } from '@/lib/utils';

export default function SectionHeader({ title, subtitle, action, className }) {
  return (
    <div className={cn('section-header', className)}>
      <div>
        {title && <h2>{title}</h2>}
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action && <div className="section-actions">{action}</div>}
    </div>
  );
}
