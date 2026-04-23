"use client"

import * as React from "react"
import { Tooltip as TooltipParts } from "radix-ui"

import { cn } from "@/lib/utils"

function TooltipProvider({
  delayDuration = 0,
  ...props
}: React.ComponentProps<typeof TooltipParts.TooltipProvider>) {
  return (
    <TooltipParts.TooltipProvider
      data-slot="tooltip-provider"
      delayDuration={delayDuration}
      {...props}
    />
  )
}

function Tooltip({
  ...props
}: React.ComponentProps<typeof TooltipParts.Root>) {
  return <TooltipParts.Root data-slot="tooltip" {...props} />
}

function TooltipTrigger({
  ...props
}: React.ComponentProps<typeof TooltipParts.TooltipTrigger>) {
  return <TooltipParts.TooltipTrigger data-slot="tooltip-trigger" {...props} />
}

function TooltipContent({
  className,
  sideOffset = 4,
  children,
  ...props
}: React.ComponentProps<typeof TooltipParts.TooltipContent>) {
  return (
    <TooltipParts.TooltipPortal>
      <TooltipParts.TooltipContent
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(
          "fade-in-0 zoom-in-95 data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 z-50 w-fit origin-(--radix-tooltip-content-transform-origin) animate-in rounded-md border bg-popover px-3 py-1.5 text-xs text-balance text-popover-foreground shadow-md data-[state=closed]:animate-out",
          className
        )}
        {...props}
      >
        {children}
      </TooltipParts.TooltipContent>
    </TooltipParts.TooltipPortal>
  )
}

export { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent }
