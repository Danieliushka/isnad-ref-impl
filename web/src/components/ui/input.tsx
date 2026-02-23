import { InputHTMLAttributes, forwardRef } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className = "", ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={`w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-[var(--foreground)] placeholder:text-white/30 focus:outline-none focus:ring-2 focus:ring-isnad-teal/50 focus:border-isnad-teal/50 transition-all duration-200 ${className}`}
        {...props}
      />
    );
  }
);

Input.displayName = "Input";
export { Input };
export type { InputProps };
