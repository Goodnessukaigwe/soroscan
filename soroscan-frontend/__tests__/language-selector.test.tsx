import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { LanguageSelector } from "@/components/ui/LanguageSelector";

const pushMock = jest.fn();
let mockPathname = "/";

jest.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({
    push: pushMock,
  }),
}));

describe("LanguageSelector", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    delete (window as any).location;
    window.location = { href: "" } as any;
    mockPathname = "/";
  });

  afterEach(() => {
    window.location = originalLocation;
  });

  it("renders a select with both supported locales", () => {
    render(<LanguageSelector />);
    const select = screen.getByLabelText(/switch language/i);
    expect(select).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "English" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Español" })).toBeInTheDocument();
  });

  it("defaults to the current locale (en)", () => {
    render(<LanguageSelector />);
    const select = screen.getByLabelText(/switch language/i) as HTMLSelectElement;
    expect(select.value).toBe("en");
  });

  it("navigates to the /es-prefixed path when switching away from the default locale", () => {
    mockPathname = "/contracts";
    render(<LanguageSelector />);
    const select = screen.getByLabelText(/switch language/i);
    fireEvent.change(select, { target: { value: "es" } });
    expect(window.location.href).toBe("/es/contracts");
  });

  it("strips the locale prefix when switching back to the default locale", () => {
    mockPathname = "/es/contracts";
    render(<LanguageSelector />);
    const select = screen.getByLabelText(/switch language/i);
    fireEvent.change(select, { target: { value: "en" } });
    expect(window.location.href).toBe("/contracts");
  });

  it("navigates to the bare /es root when on the default-locale homepage", () => {
    mockPathname = "/";
    render(<LanguageSelector />);
    const select = screen.getByLabelText(/switch language/i);
    fireEvent.change(select, { target: { value: "es" } });
    expect(window.location.href).toBe("/es");
  });
});
