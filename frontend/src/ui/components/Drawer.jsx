import {
  Drawer as BaseDrawer,
  DrawerClose,
  DrawerContent as BaseContent,
  DrawerDescription as BaseDescription,
  DrawerFooter as BaseFooter,
  DrawerHeader as BaseHeader,
  DrawerOverlay as BaseOverlay,
  DrawerPortal,
  DrawerTitle as BaseTitle,
  DrawerTrigger
} from '@/components/ui/drawer';
import { cn } from '@/lib/utils';

const Drawer = BaseDrawer;
const DrawerOverlay = ({ className, ...props }) => (
  <BaseOverlay className={cn('drawer-overlay', className)} {...props} />
);
const DrawerContent = ({ className, ...props }) => (
  <BaseContent className={cn('drawer-content', className)} {...props} />
);
const DrawerHeader = ({ className, ...props }) => (
  <BaseHeader className={cn('drawer-header', className)} {...props} />
);
const DrawerFooter = ({ className, ...props }) => (
  <BaseFooter className={cn('drawer-footer', className)} {...props} />
);
const DrawerTitle = ({ className, ...props }) => (
  <BaseTitle className={cn('drawer-title', className)} {...props} />
);
const DrawerDescription = ({ className, ...props }) => (
  <BaseDescription className={cn('drawer-description', className)} {...props} />
);

export {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  DrawerPortal,
  DrawerTitle,
  DrawerTrigger
};
