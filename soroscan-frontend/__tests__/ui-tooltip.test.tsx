import React from "react"
import { render, screen } from "@testing-library/react"
import {
  TooltipProvider,
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip"

describe("Tooltip", () => {
  it("renders tooltip content when open", () => {
    render(
      <TooltipProvider>
        <Tooltip defaultOpen>
          <TooltipTrigger asChild>
            <button type="button">More info</button>
          </TooltipTrigger>
          <TooltipContent>Helpful text</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )

    expect(screen.getByRole("tooltip")).toHaveTextContent("Helpful text")
  })

  it("forwards positioning props to content", () => {
    render(
      <TooltipProvider>
        <Tooltip defaultOpen>
          <TooltipTrigger asChild>
            <button type="button">Target</button>
          </TooltipTrigger>
          <TooltipContent side="left" align="start" data-testid="tip">
            On the left
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )

    const tip = screen.getByTestId("tip")
    expect(tip).toHaveAttribute("data-side", "left")
    expect(tip).toHaveAttribute("data-align", "start")
  })
})
