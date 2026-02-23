import { HTMLAttributes, forwardRef } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  glow?: boolean;
}

const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ glow = true, className = "", children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`bg-[var(--card-bg)] backdrop-blur-xl border border-[var(--card-border)] rounded-2xl p-6 transition-all duration-300 ${glow ? "hover:border-isnad-teal/30 hover:shadow-[0_0_30px_rgba(0,212,170,0.1)]" : ""} ${className}`}
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
