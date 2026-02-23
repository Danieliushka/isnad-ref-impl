import { ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-isnad-teal text-[#050507] font-semibold hover:bg-isnad-teal-light hover:shadow-[0_0_30px_-5px_rgba(0,212,170,0.4)] active:bg-isnad-teal-dark",
  secondary:
    "border border-white/[0.1] text-zinc-300 hover:text-white hover:bg-white/[0.05] hover:border-white/[0.15] active:bg-white/[0.08]",
  ghost:
    "text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.04] active:bg-white/[0.08]",
};

const sizeClasses: Record<Size, string> = {
  sm: "px-3.5 py-1.5 text-sm rounded-lg",
  md: "px-5 py-2.5 text-sm rounded-xl",
  lg: "px-7 py-3 text-base rounded-xl",
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className = "", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={`inline-flex items-center justify-center font-medium transition-all duration-300 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";
export { Button };
export type { ButtonProps };
