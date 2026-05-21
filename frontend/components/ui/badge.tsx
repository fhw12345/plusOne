import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-[hsl(var(--ink))] text-[hsl(var(--paper))]",
        secondary: "border-transparent bg-[hsl(var(--paper-3))] text-[hsl(var(--ink))]",
        outline: "border-[hsl(var(--ink)/0.2)] text-[hsl(var(--ink))]",
        success: "border-transparent bg-emerald-600 text-white",
        warning: "border-transparent bg-amber-600 text-white",
        danger: "border-transparent bg-red-600 text-white",
        muted: "border-transparent bg-[hsl(var(--paper-3))] text-[hsl(var(--ink-3))]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
