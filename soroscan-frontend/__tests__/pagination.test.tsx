import { fireEvent, render, screen } from "@testing-library/react"
import "@testing-library/jest-dom"
import { Pagination } from "@/src/components/ui/Pagination"

describe("Pagination", () => {
  it("renders current and total page count", () => {
    render(
      <Pagination
        totalItems={120}
        pageSize={10}
        currentPage={3}
        onPageChange={jest.fn()}
        onPageSizeChange={jest.fn()}
      />
    )

    expect(screen.getByText("Page 3 of 12")).toBeInTheDocument()
  })

  it("disables First and Previous on the first page", () => {
    render(
      <Pagination
        totalItems={50}
        pageSize={10}
        currentPage={1}
        onPageChange={jest.fn()}
        onPageSizeChange={jest.fn()}
      />
    )

    expect(screen.getByRole("button", { name: "First page" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled()
  })

  it("disables Next and Last on the final page", () => {
    render(
      <Pagination
        totalItems={50}
        pageSize={10}
        currentPage={5}
        onPageChange={jest.fn()}
        onPageSizeChange={jest.fn()}
      />
    )

    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Last page" })).toBeDisabled()
  })

  it("calls callbacks for first, previous, next, and last actions", () => {
    const onPageChange = jest.fn()

    render(
      <Pagination
        totalItems={100}
        pageSize={10}
        currentPage={5}
        onPageChange={onPageChange}
        onPageSizeChange={jest.fn()}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "First page" }))
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }))
    fireEvent.click(screen.getByRole("button", { name: "Next page" }))
    fireEvent.click(screen.getByRole("button", { name: "Last page" }))

    expect(onPageChange).toHaveBeenNthCalledWith(1, 1)
    expect(onPageChange).toHaveBeenNthCalledWith(2, 4)
    expect(onPageChange).toHaveBeenNthCalledWith(3, 6)
    expect(onPageChange).toHaveBeenNthCalledWith(4, 10)
  })

  it("supports direct page number jumping", () => {
    const onPageChange = jest.fn()

    render(
      <Pagination
        totalItems={100}
        pageSize={10}
        currentPage={5}
        onPageChange={onPageChange}
        onPageSizeChange={jest.fn()}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "Go to page 4" }))
    expect(onPageChange).toHaveBeenCalledWith(4)
  })

  it("marks active page with aria-current=page", () => {
    render(
      <Pagination
        totalItems={100}
        pageSize={10}
        currentPage={5}
        onPageChange={jest.fn()}
        onPageSizeChange={jest.fn()}
      />
    )

    expect(screen.getByRole("button", { name: "Go to page 5" })).toHaveAttribute("aria-current", "page")
  })

  it("renders ellipsis for large page ranges", () => {
    render(
      <Pagination
        totalItems={500}
        pageSize={10}
        currentPage={10}
        onPageChange={jest.fn()}
        onPageSizeChange={jest.fn()}
      />
    )

    expect(screen.getAllByText("...").length).toBeGreaterThan(0)
  })

  it("calls onPageSizeChange when selecting page size", () => {
    const onPageSizeChange = jest.fn()

    render(
      <Pagination
        totalItems={100}
        pageSize={10}
        currentPage={1}
        onPageChange={jest.fn()}
        onPageSizeChange={onPageSizeChange}
      />
    )

    fireEvent.change(screen.getByLabelText("Page size"), { target: { value: "20" } })
    expect(onPageSizeChange).toHaveBeenCalledWith(20)
  })
})
