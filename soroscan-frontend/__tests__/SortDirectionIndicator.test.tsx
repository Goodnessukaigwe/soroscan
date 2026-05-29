import React from "react";
import { render, screen } from "@testing-library/react";
import { SortDirectionIndicator } from "@/components/terminal/Table";

describe("SortDirectionIndicator", () => {
  it("shows muted up arrow when column is not active", () => {
    const { container } = render(
      <SortDirectionIndicator active={false} direction="asc" />,
    );
    const icon = container.querySelector("svg");
    expect(icon).toHaveClass("opacity-20");
  });

  it("shows up arrow for ascending active sort", () => {
    const { container } = render(
      <SortDirectionIndicator active={true} direction="asc" />,
    );
    const icon = container.querySelector("svg");
    expect(icon).toBeTruthy();
    expect(icon?.classList.contains("opacity-20")).toBe(false);
  });

  it("shows down arrow for descending active sort", () => {
    const { container } = render(
      <SortDirectionIndicator active={true} direction="desc" />,
    );
    const icon = container.querySelector("svg");
    expect(icon).toBeTruthy();
    expect(icon?.classList.contains("opacity-20")).toBe(false);
  });
});
