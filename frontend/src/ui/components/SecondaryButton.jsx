import React from 'react';
import { cn } from '@/lib/utils';

export default function SecondaryButton({ className, ...props }) {
  return <button className={cn('btn-secondary', className)} {...props} />;
}
