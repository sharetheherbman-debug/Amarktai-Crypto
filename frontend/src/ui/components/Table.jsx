import React from 'react';
import { cn } from '@/lib/utils';

export default function Table({ className, ...props }) {
  return <div className={cn('table-shell', className)}><table {...props} /></div>;
}
