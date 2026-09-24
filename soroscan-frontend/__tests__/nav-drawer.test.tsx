import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { Drawer } from "@/components/ui/drawer";
import { HamburgerToggle } from "@/components/ui/hamburger-toggle";
import { NavDrawer } from "@/components/terminal/landing/NavDrawer";

// ── Mock next/navigation (usePathname, useRouter) ──────────────────
jest.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({
    push: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
}));

// ── Mock @/lib/auth ────────────────────────────────────────────────
jest.mock("@/lib/auth", () => ({
  isLoggedIn: jest.fn(() => false),
  clearTokens: jest.fn(),
  getAccessToken: jest.fn(() => null),
  getRefreshToken: jest.fn(() => null),
  setTokens: jest.fn(),
  refreshAccessToken: jest.fn(),
}));

// ── Mock next/link to simple <a> ───────────────────────────────────
jest.mock("next/link", () => {
  const MockLink = ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

describe("Drawer Base Component", () => {
  it("renders when isOpen is true", () => {
    render(
      <Drawer isOpen={true} onClose={() => {}} title="Test Drawer">
        <div>Drawer Content</div>
      </Drawer>
    );
    expect(screen.getByText("Test Drawer")).toBeInTheDocument();
    expect(screen.getByText("Drawer Content")).toBeInTheDocument();
  });

  it("does not render when isOpen is false", () => {
    const { container } = render(
      <Drawer isOpen={false} onClose={() => {}} title="Test Drawer">
        <div>Drawer Content</div>
      </Drawer>
    );
    expect(container.firstChild).toBeNull();
  });

  it("calls onClose when the close button is clicked", () => {
    const handleClose = jest.fn();
    render(
      <Drawer isOpen={true} onClose={handleClose} title="Test Drawer">
        <div>Drawer Content</div>
      </Drawer>
    );
    const closeBtn = screen.getByRole("button", { name: /close drawer/i });
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when backdrop is clicked", () => {
    const handleClose = jest.fn();
    render(
      <Drawer isOpen={true} onClose={handleClose} title="Test Drawer">
        <div>Drawer Content</div>
      </Drawer>
    );
    const backdrop = screen.getByRole("dialog").previousSibling;
    expect(backdrop).toBeInTheDocument();
    if (backdrop) {
      fireEvent.click(backdrop);
      expect(handleClose).toHaveBeenCalledTimes(1);
    }
  });
});

describe("HamburgerToggle Component", () => {
  it("renders with correct ARIA attributes when closed", () => {
    render(<HamburgerToggle isOpen={false} onClick={() => {}} ariaControls="nav-menu" />);
    const toggle = screen.getByRole("button", { name: /toggle menu/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAttribute("aria-controls", "nav-menu");
  });

  it("renders with correct ARIA attributes when open", () => {
    render(<HamburgerToggle isOpen={true} onClick={() => {}} ariaControls="nav-menu" />);
    const toggle = screen.getByRole("button", { name: /close menu/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("triggers onClick when clicked", () => {
    const handleClick = jest.fn();
    render(<HamburgerToggle isOpen={false} onClick={handleClick} />);
    const toggle = screen.getByRole("button", { name: /toggle menu/i });
    fireEvent.click(toggle);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
});

describe("NavDrawer Component", () => {
  it("renders navigation items", () => {
    render(
      <NavDrawer
        isOpen={true}
        onClose={() => {}}
        authenticated={false}
        handleLogout={() => {}}
        pathname="/"
      />
    );
    expect(screen.getByText("Documentation")).toBeInTheDocument();
    expect(screen.getByText("Features")).toBeInTheDocument();
    expect(screen.getByText("API_Explorer")).toBeInTheDocument();
    expect(screen.getByText("GITHUB")).toBeInTheDocument();
    expect(screen.getByText("Login")).toBeInTheDocument();
  });

  it("renders logout button when authenticated", () => {
    render(
      <NavDrawer
        isOpen={true}
        onClose={() => {}}
        authenticated={true}
        handleLogout={() => {}}
        pathname="/"
      />
    );
    expect(screen.getByText("Logout")).toBeInTheDocument();
    expect(screen.queryByText("Login")).not.toBeInTheDocument();
  });

  it("triggers onClose when a navigation item is clicked", () => {
    const handleClose = jest.fn();
    render(
      <NavDrawer
        isOpen={true}
        onClose={handleClose}
        authenticated={false}
        handleLogout={() => {}}
        pathname="/"
      />
    );
    const docsLink = screen.getByText("Documentation");
    fireEvent.click(docsLink);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
