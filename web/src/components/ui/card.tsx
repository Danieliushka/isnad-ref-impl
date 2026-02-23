import { HTMLAttributes, forwardRef } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  glow?: boolean;
}

const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ glow = true, className = "", children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`relative bg-white/[0.02] backdrop-blur-xl border border-white/[0.06] rounded-2xl p-6 transition-all duration-500 ${
          glow
            ? "hover:border-isnad-teal/20 hover:bg-white/[0.04] hover:shadow-[0_0_40px_-10px_rgba(0,212,170,0.12)]"
            : ""
        } ${className}`}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = "Card";
export { Card };
export type { CardProps };
