import React from "react"
import { fireEvent, render, screen, within } from "@testing-library/react"
import {
  ContractTable,
  sortContracts,
  type SortableContract,
} from "@/app/contracts/components/ContractTable"

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}))

const CONTRACTS: SortableContract[] = [
  {
    id: "ctr-c",
    contractId: "CCCCC",
    name: "Charlie",
    status: "active",
    eventCount: 10,
    createdAt: "2026-03-01T00:00:00.000Z",
    updatedAt: "2026-03-05T00:00:00.000Z",
    lastEventTime: "2026-03-05T00:00:00.000Z",
    tags: [],
  },
  {
    id: "ctr-a",
    contractId: "CCAAA",
    name: "alpha",
    status: "inactive",
    eventCount: 30,
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-02-02T00:00:00.000Z",
    lastEventTime: "2026-02-02T00:00:00.000Z",
    tags: [],
  },
  {
    id: "ctr-b",
    contractId: "CCBBB",
    name: "Bravo",
    status: "active",
    eventCount: 20,
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-02-02T00:00:00.000Z",
    lastEventTime: undefined,
    tags: [],
  },
  {
    id: "ctr-d",
    contractId: "CCDDD",
    name: "delta",
    status: "active",
    eventCount: 40,
    createdAt: "2026-02-01T00:00:00.000Z",
    updatedAt: "2026-04-01T00:00:00.000Z",
    lastEventTime: "2026-04-01T00:00:00.000Z",
    tags: [],
  },
]

function renderTable() {
  return render(
    <ContractTable
      contracts={CONTRACTS}
      onDelete={jest.fn()}
      onRegister={jest.fn()}
    />,
  )
}

function desktopTable() {
  return within(screen.getByTestId("contract-desktop-table"))
}

function displayedNames() {
  return desktopTable()
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[2]?.textContent)
}

describe("ContractTable sorting", () => {
  it("sorts names case-insensitively by default", () => {
    renderTable()
    expect(displayedNames()).toEqual(["alpha", "Bravo", "Charlie", "delta"])
    expect(desktopTable().getByTestId("sort-name").closest("th")).toHaveAttribute(
      "aria-sort",
      "ascending",
    )
  })

  it("toggles the active column between ascending and descending", () => {
    renderTable()
    const nameSort = desktopTable().getByTestId("sort-name")

    fireEvent.click(nameSort)
    expect(displayedNames()).toEqual(["delta", "Charlie", "Bravo", "alpha"])
    expect(nameSort.closest("th")).toHaveAttribute("aria-sort", "descending")
    expect(nameSort.querySelector("svg")).not.toHaveClass("opacity-20")

    fireEvent.click(nameSort)
    expect(displayedNames()).toEqual(["alpha", "Bravo", "Charlie", "delta"])
    expect(nameSort.closest("th")).toHaveAttribute("aria-sort", "ascending")
  })

  it("resets a newly selected column to ascending", () => {
    renderTable()
    const nameSort = desktopTable().getByTestId("sort-name")
    const createdSort = desktopTable().getByTestId("sort-createdAt")

    fireEvent.click(nameSort)
    fireEvent.click(createdSort)

    expect(nameSort.closest("th")).toHaveAttribute("aria-sort", "none")
    expect(createdSort.closest("th")).toHaveAttribute("aria-sort", "ascending")
    expect(displayedNames()).toEqual(["alpha", "Bravo", "delta", "Charlie"])
  })

  it("keeps rows with no last event at the end in both directions", () => {
    renderTable()
    const lastEventSort = desktopTable().getByTestId("sort-lastEventTime")

    fireEvent.click(lastEventSort)
    expect(displayedNames()).toEqual(["alpha", "Charlie", "delta", "Bravo"])

    fireEvent.click(lastEventSort)
    expect(displayedNames()).toEqual(["delta", "Charlie", "alpha", "Bravo"])
  })

  it("uses the contract id as a deterministic tie-breaker", () => {
    const sorted = sortContracts(CONTRACTS, "createdAt", "asc")
    expect(sorted.slice(0, 2).map((contract) => contract.id)).toEqual([
      "ctr-a",
      "ctr-b",
    ])
  })
})
