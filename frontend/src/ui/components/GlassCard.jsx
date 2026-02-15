import React from 'react';
import { cn } from '@/lib/utils';

export default function GlassCard({ as: Component = 'div', className, ...props }) {
  return <Component className={cn('glass-card', className)} {...props} />;
}
