import { render, screen, fireEvent, within } from "@testing-library/react";
import { TeamMembersTable } from "@/components/organization/TeamMembersTable";
import { RolePermissionMatrix } from "@/components/organization/RolePermissionMatrix";
import { OrganizationSettingsPage } from "@/components/organization/OrganizationSettingsPage";
import { TypeConfirmDialog } from "@/components/organization/TypeConfirmDialog";
import { OrganizationSwitcher } from "@/components/organization/OrganizationSwitcher";
import {
  __resetOrganizationStoreForTests,
  listTeamMembers,
  updateTeamMemberRole,
} from "@/lib/organization-store";
import type { Organization, TeamMember } from "@/lib/organization";

jest.mock("@/lib/organization-store", () => {
  const actual = jest.requireActual("@/lib/organization-store");
  return {
    ...actual,
    // Delegate to the real implementation by default so the rest of this file
    // exercises the localStorage-backed store; individual tests override it to
    // simulate a failed write.
    updateTeamMemberRole: jest.fn(actual.updateTeamMemberRole),
  };
});

const mockedUpdateTeamMemberRole = updateTeamMemberRole as jest.MockedFunction<
  typeof updateTeamMemberRole
>;

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

const org: Organization = {
  id: "org_acme",
  name: "Acme Indexing",
  billingContact: "billing@acme.dev",
  dataRegion: "us-east",
  createdAt: "2026-01-10T12:00:00.000Z",
  contractCount: 12,
  webhookLimit: 50,
};

describe("organization UI (#913)", () => {
  beforeEach(() => {
    localStorage.clear();
    __resetOrganizationStoreForTests();
  });

  it("renders organization switcher when user belongs to multiple orgs", () => {
    render(<OrganizationSwitcher />);
    expect(
      screen.getByRole("button", { name: /switch organization/i }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /switch organization/i }));
    expect(screen.getByRole("listbox", { name: /organizations/i })).toBeInTheDocument();
    expect(screen.getByText("Nebula Labs")).toBeInTheDocument();
  });

  it("shows read-only settings for viewers", () => {
    render(
      <OrganizationSettingsPage
        organization={org}
        currentRole="viewer"
        onUpdated={jest.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/read-only/i);
    expect(screen.queryByRole("button", { name: /save settings/i })).not.toBeInTheDocument();
  });

  it("hides member management actions for non-owners/admins", () => {
    const members = listTeamMembers("org_acme");
    render(
      <TeamMembersTable
        organizationId="org_acme"
        members={members}
        currentRole="viewer"
        onChanged={jest.fn()}
        onRequestRemove={jest.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/read-only/i);
    expect(screen.queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
  });

  it("allows owners to change roles inline", () => {
    const members = listTeamMembers("org_acme");
    const onChanged = jest.fn();
    render(
      <TeamMembersTable
        organizationId="org_acme"
        members={members}
        currentRole="owner"
        onChanged={onChanged}
        onRequestRemove={jest.fn()}
      />,
    );
    const select = screen.getByLabelText(/role for bob@acme.dev/i);
    fireEvent.change(select, { target: { value: "viewer" } });
    expect(onChanged).toHaveBeenCalled();
  });

  it("surfaces a role-change failure instead of crashing the table", () => {
    const members = listTeamMembers("org_acme");
    const onChanged = jest.fn();
    mockedUpdateTeamMemberRole.mockImplementationOnce(() => {
      throw new Error("Failed to connect to API");
    });

    render(
      <TeamMembersTable
        organizationId="org_acme"
        members={members}
        currentRole="owner"
        onChanged={onChanged}
        onRequestRemove={jest.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/role for bob@acme.dev/i), {
      target: { value: "viewer" },
    });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Failed to connect to API");
    // The table still renders its rows rather than blowing up.
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("bob@acme.dev")).toBeInTheDocument();
    // The failed write must not be reported as a successful change.
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("falls back to a generic message when the failure carries no text", () => {
    const members = listTeamMembers("org_acme");
    mockedUpdateTeamMemberRole.mockImplementationOnce(() => {
      throw "not-an-error-object";
    });

    render(
      <TeamMembersTable
        organizationId="org_acme"
        members={members}
        currentRole="owner"
        onChanged={jest.fn()}
        onRequestRemove={jest.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/role for bob@acme.dev/i), {
      target: { value: "viewer" },
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Failed to update role");
  });

  it("clears a previous error once a role change succeeds", () => {
    const members = listTeamMembers("org_acme");
    mockedUpdateTeamMemberRole.mockImplementationOnce(() => {
      throw new Error("Failed to connect to API");
    });

    render(
      <TeamMembersTable
        organizationId="org_acme"
        members={members}
        currentRole="owner"
        onChanged={jest.fn()}
        onRequestRemove={jest.fn()}
      />,
    );

    const select = screen.getByLabelText(/role for bob@acme.dev/i);
    fireEvent.change(select, { target: { value: "viewer" } });
    expect(screen.getByRole("alert")).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "operator" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("requires typing the email to confirm member removal", () => {
    const member: TeamMember = {
      id: "mem_bob",
      email: "bob@acme.dev",
      role: "operator",
      joinedAt: "2026-02-01T11:00:00.000Z",
      lastActiveAt: null,
    };
    const onConfirm = jest.fn();
    render(
      <TypeConfirmDialog
        open
        title="REMOVE_MEMBER"
        description="This will revoke access."
        confirmPhrase={member.email}
        confirmText="Remove member"
        onConfirm={onConfirm}
        onCancel={jest.fn()}
      />,
    );
    const confirm = screen.getByRole("button", { name: /remove member/i });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/confirmation/i), {
      target: { value: member.email },
    });
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalled();
  });

  it("renders the role permission matrix", () => {
    render(<RolePermissionMatrix />);
    expect(screen.getByText(/manage organization settings/i)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Owner")).toBeInTheDocument();
  });
});
