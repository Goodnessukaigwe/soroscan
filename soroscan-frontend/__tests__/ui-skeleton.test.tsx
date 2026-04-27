import React from "react"
import { render, screen } from "@testing-library/react"
import { Skeleton } from "@/components/ui/skeleton"

describe("Skeleton Component", () => {
  it("renders a div with aria-hidden and data-slot attributes", () => {
    render(<Skeleton data-testid="skeleton" />)
    const el = screen.getByTestId("skeleton")
    expect(el).toBeInTheDocument()
    expect(el).toHaveAttribute("aria-hidden", "true")
    expect(el).toHaveAttribute("data-slot", "skeleton")
  })

  it("renders the rectangle variant with rounded-md by default", () => {
    render(<Skeleton data-testid="rect" />)
    expect(screen.getByTestId("rect")).toHaveClass("rounded-md")
  })

  it("renders the circle variant with rounded-full", () => {
    render(<Skeleton variant="circle" data-testid="circle" />)
    expect(screen.getByTestId("circle")).toHaveClass("rounded-full")
  })

  it("renders the text variant with h-4 and w-full", () => {
    render(<Skeleton variant="text" data-testid="text" />)
    const el = screen.getByTestId("text")
    expect(el).toHaveClass("h-4", "w-full")
  })

  it("applies numeric width and height as pixel inline styles", () => {
    render(<Skeleton width={120} height={80} data-testid="sized" />)
    expect(screen.getByTestId("sized")).toHaveStyle({ width: "120px", height: "80px" })
  })

  it("applies string width and height values as-is", () => {
    render(<Skeleton width="50%" height="2rem" data-testid="str-sized" />)
    expect(screen.getByTestId("str-sized")).toHaveStyle({ width: "50%", height: "2rem" })
  })

  it("applies the shimmer animation class", () => {
    render(<Skeleton data-testid="shimmer" />)
    expect(screen.getByTestId("shimmer")).toHaveClass("animate-shimmer")
  })

  it("forwards ref to the root div", () => {
    const ref = React.createRef<HTMLDivElement>()
    render(<Skeleton ref={ref} />)
    expect(ref.current).not.toBeNull()
    expect(ref.current?.tagName).toBe("DIV")
    expect(ref.current?.getAttribute("aria-hidden")).toBe("true")
  })

  it("merges extra className without losing base classes", () => {
    render(<Skeleton className="mt-4" data-testid="merged" />)
    const el = screen.getByTestId("merged")
    expect(el).toHaveClass("mt-4")
    expect(el).toHaveClass("rounded-md")
  })

  it("does not expose a semantic role in the accessibility tree", () => {
    render(<Skeleton data-testid="no-role" />)
    expect(screen.queryByRole("img")).toBeNull()
    expect(screen.queryByRole("status")).toBeNull()
  })
})
