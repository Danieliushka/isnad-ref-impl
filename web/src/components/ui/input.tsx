import { InputHTMLAttributes, forwardRef } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className = "", ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={`w-full bg-white/[0.03] border border-white/[0.08] rounded-xl px-4 py-3 text-[var(--foreground)] placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-isnad-teal/30 focus:border-isnad-teal/30 transition-all duration-300 font-mono text-sm ${className}`}
        {...props}
      />
    );
  }
);

Input.displayName = "Input";
export { Input };
export type { InputProps };
