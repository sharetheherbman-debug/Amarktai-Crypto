import React from 'react';
import { cn } from '@/lib/utils';

export default function Badge({ variant = 'default', className, children, ...props }) {
  return (
    <span className={cn('badge', `badge-${variant}`, className)} {...props}>
      {children}
    </span>
  );
}
