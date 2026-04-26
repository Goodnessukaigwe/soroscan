import React from "react"
import { render, screen } from "@testing-library/react"
import { Divider } from "@/components/ui/divider"

describe("Divider Component", () => {
  it("renders a horizontal separator by default with correct ARIA attributes", () => {
    render(<Divider />)
    const divider = screen.getByRole("separator")
    expect(divider).toBeInTheDocument()
    expect(divider).toHaveAttribute("aria-orientation", "horizontal")
  })

  it("renders a vertical separator with correct ARIA attributes", () => {
    render(<Divider orientation="vertical" />)
    const divider = screen.getByRole("separator")
    expect(divider).toHaveAttribute("aria-orientation", "vertical")
    expect(divider).toHaveClass("w-px", "h-full")
  })

  it("applies subtle and prominent variants", () => {
    const { rerender } = render(<Divider variant="subtle" data-testid="divider" />)
    expect(screen.getByTestId("divider")).toHaveClass("opacity-40")

    rerender(<Divider variant="prominent" data-testid="divider" />)
    expect(screen.getByTestId("divider")).toHaveClass("opacity-100")
  })

  it("centers a label between two lines when label prop is set", () => {
    render(<Divider label="or continue with" />)
    expect(screen.getByText("or continue with")).toBeInTheDocument()
    const separator = screen.getByRole("separator")
    expect(separator).toHaveAttribute("aria-orientation", "horizontal")
  })

  it("applies correct styling classes to the label span", () => {
    render(<Divider label="Section" />)
    const labelEl = screen.getByText("Section")
    expect(labelEl.tagName).toBe("SPAN")
    expect(labelEl).toHaveClass("text-sm", "text-muted-foreground", "whitespace-nowrap")
  })

  it("renders two line divs flanking the label text", () => {
    render(<Divider label="OR" data-testid="labeled-divider" />)
    const container = screen.getByTestId("labeled-divider")
    const lineDivs = Array.from(container.children).filter(
      (child) => child.tagName === "DIV"
    )
    expect(lineDivs).toHaveLength(2)
  })

  it("applies a custom color via inline style on a plain divider", () => {
    render(<Divider color="#ff3366" data-testid="colored-divider" />)
    expect(screen.getByTestId("colored-divider")).toHaveStyle({
      backgroundColor: "#ff3366",
    })
  })

  it("applies custom color to both line divs when label is present", () => {
    render(<Divider label="With Color" color="#cc0000" data-testid="labeled-divider" />)
    const container = screen.getByTestId("labeled-divider")
    const lineDivs = container.querySelectorAll<HTMLElement>(":scope > div")
    expect(lineDivs).toHaveLength(2)
    lineDivs.forEach((line) => {
      expect(line.style.backgroundColor).toBeTruthy()
    })
  })

  it("forwards ref to the root separator element", () => {
    const ref = React.createRef<HTMLDivElement>()
    render(<Divider ref={ref} />)
    expect(ref.current).not.toBeNull()
    expect(ref.current?.getAttribute("role")).toBe("separator")
  })

  it("merges additional className onto the root element", () => {
    render(<Divider className="my-8" data-testid="classed-divider" />)
    expect(screen.getByTestId("classed-divider")).toHaveClass("my-8")
  })
})
