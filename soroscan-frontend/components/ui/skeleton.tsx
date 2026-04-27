import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const skeletonVariants = cva(
  "animate-shimmer bg-[length:200%_100%] bg-gradient-to-r from-muted via-muted-foreground/10 to-muted",
  {
    variants: {
      variant: {
        rectangle: "rounded-md",
        circle: "rounded-full",
        text: "rounded h-4 w-full",
      },
    },
    defaultVariants: {
      variant: "rectangle",
    },
  }
)

type DimensionValue = string | number

function toCSSValue(val: DimensionValue | undefined): string | undefined {
  if (val === undefined) return undefined
  return typeof val === "number" ? `${val}px` : val
}

interface SkeletonProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof skeletonVariants> {
  width?: DimensionValue
  height?: DimensionValue
}

const Skeleton = React.forwardRef<HTMLDivElement, SkeletonProps>(
  ({ className, variant = "rectangle", width, height, style, ...props }, ref) => {
    const dimensionStyle: React.CSSProperties = {
      width: toCSSValue(width),
      height: toCSSValue(height),
      ...style,
    }

    return (
      <div
        ref={ref}
        data-slot="skeleton"
        className={cn(skeletonVariants({ variant }), className)}
        style={dimensionStyle}
        {...props}
        aria-hidden="true"
      />
    )
  }
)
Skeleton.displayName = "Skeleton"

export { Skeleton, skeletonVariants }
