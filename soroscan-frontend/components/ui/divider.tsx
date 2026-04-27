import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const dividerVariants = cva("bg-border", {
  variants: {
    orientation: {
      horizontal: "w-full h-px",
      vertical: "h-full w-px",
    },
    variant: {
      subtle: "opacity-40",
      prominent: "opacity-100",
    },
  },
  defaultVariants: {
    orientation: "horizontal",
    variant: "subtle",
  },
})

interface DividerProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof dividerVariants> {
  label?: string
  color?: string
}

const Divider = React.forwardRef<HTMLDivElement, DividerProps>(
  (
    {
      className,
      orientation = "horizontal",
      variant = "subtle",
      label,
      color,
      style,
      ...props
    },
    ref
  ) => {
    const lineStyle: React.CSSProperties = color
      ? { backgroundColor: color, ...style }
      : { ...style }

    if (orientation === "horizontal" && label) {
      return (
        <div
          ref={ref}
          role="separator"
          aria-orientation="horizontal"
          data-slot="divider"
          className={cn("flex items-center gap-3 w-full", className)}
          {...props}
        >
          <div
            className={cn(dividerVariants({ orientation: "horizontal", variant }), "flex-1")}
            style={lineStyle}
          />
          <span className="text-sm text-muted-foreground whitespace-nowrap">{label}</span>
          <div
            className={cn(dividerVariants({ orientation: "horizontal", variant }), "flex-1")}
            style={lineStyle}
          />
        </div>
      )
    }

    return (
      <div
        ref={ref}
        role="separator"
        aria-orientation={orientation ?? "horizontal"}
        data-slot="divider"
        className={cn(dividerVariants({ orientation, variant }), className)}
        style={lineStyle}
        {...props}
      />
    )
  }
)
Divider.displayName = "Divider"

export { Divider, dividerVariants }
