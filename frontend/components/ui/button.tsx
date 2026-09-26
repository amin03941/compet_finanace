import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const boutonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-colors " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action/40 disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primaire: "bg-action text-white shadow-sm hover:bg-action/90",
        marine: "bg-marine text-white shadow-sm hover:bg-marine/90 dark:bg-action dark:hover:bg-action/90",
        secondaire: "border border-ligne bg-carte text-encre hover:bg-survol",
        fantome: "text-attenue hover:bg-survol hover:text-encre",
        danger: "bg-rouge text-white hover:bg-rouge/90",
        succes: "bg-vert text-white hover:bg-vert/90",
      },
      taille: { md: "h-10 px-4", sm: "h-8 px-3 text-xs", lg: "h-11 px-5", icone: "h-9 w-9" },
    },
    defaultVariants: { variant: "primaire", taille: "md" },
  },
);

export interface BoutonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof boutonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, BoutonProps>(({ className, variant, taille, asChild, ...props }, ref) => {
  const Comp = asChild ? Slot : "button";
  return <Comp ref={ref} className={cn(boutonVariants({ variant, taille }), className)} {...props} />;
});
Button.displayName = "Button";
