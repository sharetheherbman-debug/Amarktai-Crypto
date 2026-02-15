import React from 'react';
import { cn } from '@/lib/utils';

export default function PrimaryButton({ className, ...props }) {
  return <button className={cn('btn-primary', className)} {...props} />;
}
