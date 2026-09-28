import * as React from "react"
import { cn } from "@/lib/utils"
import { ChevronRight, Slash } from "lucide-react"

interface BreadcrumbItem {
  label: string
  href?: string
}

interface BreadcrumbProps extends React.HTMLAttributes<HTMLElement> {
  items: BreadcrumbItem[]
  separator?: "chevron" | "slash"
  maxItems?: number
}

const separatorIcons = {
  chevron: ChevronRight,
  slash: Slash,
} as const

const CONTRACT_ID_LENGTH = 56

function isContractId(label: string): boolean {
  return label.length === CONTRACT_ID_LENGTH && label.startsWith("C")
}

function truncateContractId(label: string): string {
  return isContractId(label) ? `${label.slice(0, 4)}...${label.slice(-4)}` : label
}

const Breadcrumb = React.forwardRef<HTMLElement, BreadcrumbProps>(
  ({ className, items, separator = "chevron", maxItems, ...props }, ref) => {
    const SeparatorIcon = separatorIcons[separator]

    const visibleItems = maxItems && items.length > maxItems
      ? [
          ...items.slice(0, 1),
          { label: "...", href: undefined },
          ...items.slice(-(maxItems - 2)),
        ]
      : items

    return (
      <nav
        ref={ref}
        aria-label="Breadcrumb"
        data-slot="breadcrumb"
        className={cn("flex items-center text-sm text-muted-foreground", className)}
        {...props}
      >
        <ol className="flex items-center gap-1.5 flex-wrap">
          {visibleItems.map((item, index) => {
            const isLast = index === visibleItems.length - 1
            const shortLabel = truncateContractId(item.label)
            const isTruncated = shortLabel !== item.label

            return (
              <li key={`${item.label}-${index}`} className="flex items-center gap-1.5">
                {index > 0 && (
                  <SeparatorIcon
                    aria-hidden="true"
                    className="h-4 w-4 shrink-0 text-muted-foreground/50"
                  />
                )}
                {item.href && !isLast ? (
                  <a
                    href={item.href}
                    title={isTruncated ? item.label : undefined}
                    className="hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-sm"
                  >
                    {shortLabel}
                  </a>
                ) : (
                  <span
                    aria-current={isLast ? "page" : undefined}
                    title={isTruncated ? item.label : undefined}
                    className={cn(
                      isLast && "text-foreground font-medium"
                    )}
                  >
                    {shortLabel}
                  </span>
                )}
              </li>
            )
          })}
        </ol>
      </nav>
    )
  }
)
Breadcrumb.displayName = "Breadcrumb"

export { Breadcrumb }
export type { BreadcrumbItem, BreadcrumbProps }
