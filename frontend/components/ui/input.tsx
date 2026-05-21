import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        ref={ref}
        className={cn(
          "border border-[hsl(var(--ink)/0.2)] bg-[hsl(var(--paper-2))] text-[hsl(var(--ink))] placeholder:text-[hsl(var(--ink-3))] flex h-9 w-full rounded-md px-3 py-1 text-sm shadow-sm transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
