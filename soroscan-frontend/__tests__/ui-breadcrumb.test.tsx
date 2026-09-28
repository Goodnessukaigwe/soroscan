import React from "react"
import { render, screen } from "@testing-library/react"
import { Breadcrumb } from "@/components/ui/breadcrumb"

const defaultItems = [
  { label: "Home", href: "/" },
  { label: "Dashboard", href: "/dashboard" },
  { label: "Events" },
]

const contractId = `C${"A".repeat(51)}WXYZ`
const truncatedContractId = "CAAA...WXYZ"

describe("Breadcrumb Component", () => {
  it("renders all items", () => {
    render(<Breadcrumb items={defaultItems} data-testid="breadcrumb" />)
    expect(screen.getByText("Home")).toBeInTheDocument()
    expect(screen.getByText("Dashboard")).toBeInTheDocument()
    expect(screen.getByText("Events")).toBeInTheDocument()
  })

  it("renders links for non-last items with href", () => {
    render(<Breadcrumb items={defaultItems} />)
    const homeLink = screen.getByText("Home").closest("a")
    expect(homeLink).toHaveAttribute("href", "/")
    const dashLink = screen.getByText("Dashboard").closest("a")
    expect(dashLink).toHaveAttribute("href", "/dashboard")
  })

  it("renders last item as plain text with aria-current", () => {
    render(<Breadcrumb items={defaultItems} />)
    const lastItem = screen.getByText("Events")
    expect(lastItem).toHaveAttribute("aria-current", "page")
    expect(lastItem).toHaveClass("font-medium")
  })

  it("renders chevron separators by default", () => {
    const { container } = render(<Breadcrumb items={defaultItems} />)
    const chevrons = container.querySelectorAll("svg.lucide-chevron-right")
    expect(chevrons).toHaveLength(2)
  })

  it("renders slash separators when specified", () => {
    const { container } = render(<Breadcrumb items={defaultItems} separator="slash" />)
    const slashes = container.querySelectorAll("svg.lucide-slash")
    expect(slashes).toHaveLength(2)
  })

  it("has correct aria-label", () => {
    render(<Breadcrumb items={defaultItems} />)
    expect(screen.getByLabelText("Breadcrumb")).toBeInTheDocument()
  })

  it("collapses items when maxItems is set", () => {
    const manyItems = [
      { label: "Home", href: "/" },
      { label: "Section", href: "/section" },
      { label: "Category", href: "/category" },
      { label: "Subcategory", href: "/subcategory" },
      { label: "Item" },
    ]
    render(<Breadcrumb items={manyItems} maxItems={3} />)
    expect(screen.getByText("Home")).toBeInTheDocument()
    expect(screen.getByText("...")).toBeInTheDocument()
    expect(screen.getByText("Item")).toBeInTheDocument()
  })

  it("applies custom className", () => {
    render(<Breadcrumb items={defaultItems} className="custom-class" />)
    expect(screen.getByLabelText("Breadcrumb")).toHaveClass("custom-class")
  })

  it("forwards ref", () => {
    const ref = React.createRef<HTMLElement>()
    render(<Breadcrumb items={defaultItems} ref={ref} />)
    expect(ref.current).not.toBeNull()
    expect(ref.current?.tagName).toBe("NAV")
  })

  it("has data-slot attribute", () => {
    render(<Breadcrumb items={defaultItems} data-testid="breadcrumb" />)
    expect(screen.getByTestId("breadcrumb")).toHaveAttribute("data-slot", "breadcrumb")
  })

  it("truncates contract IDs and keeps the full ID in a title", () => {
    render(<Breadcrumb items={[{ label: contractId }]} />)
    const truncated = screen.getByText(truncatedContractId)
    expect(truncated).toHaveAttribute("title", contractId)
    expect(screen.queryByText(contractId)).not.toBeInTheDocument()
  })

  it("truncates contract IDs in link items too", () => {
    render(
      <Breadcrumb
        items={[
          { label: "Contracts", href: "/contracts" },
          { label: contractId, href: `/contracts/${contractId}` },
          { label: "Details" },
        ]}
      />,
    )
    const link = screen.getByText(truncatedContractId).closest("a")
    expect(link).toHaveAttribute("title", contractId)
    expect(link).toHaveAttribute("href", `/contracts/${contractId}`)
  })

  it("leaves ordinary labels unchanged", () => {
    render(<Breadcrumb items={defaultItems} />)
    for (const label of ["Home", "Dashboard", "Events"]) {
      expect(screen.getByText(label)).not.toHaveAttribute("title")
    }
  })

  it("does not truncate the collapsed-items ellipsis", () => {
    render(
      <Breadcrumb
        items={[
          { label: "Home" },
          { label: "Section" },
          { label: contractId },
          { label: "Details" },
        ]}
        maxItems={3}
      />,
    )
    expect(screen.getByText("...")).not.toHaveAttribute("title")
  })
})
