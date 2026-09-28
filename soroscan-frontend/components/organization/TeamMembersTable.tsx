"use client";

import * as React from "react";
import { ArrowDownAZ, ArrowUpAZ } from "lucide-react";
import { Button } from "@/components/terminal/Button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/terminal/Table";
import {
  ORG_ROLE_LABELS,
  canManageMembers,
  type OrgRole,
  type TeamMember,
} from "@/lib/organization";
import { updateTeamMemberRole } from "@/lib/organization-store";

type SortKey = "email" | "role" | "joinedAt";

interface TeamMembersTableProps {
  organizationId: string;
  members: TeamMember[];
  currentRole: OrgRole | null;
  onChanged: () => void;
  onRequestRemove: (member: TeamMember) => void;
}

export function TeamMembersTable({
  organizationId,
  members,
  currentRole,
  onChanged,
  onRequestRemove,
}: TeamMembersTableProps) {
  const canManage = canManageMembers(currentRole);
  const [sortKey, setSortKey] = React.useState<SortKey>("email");
  const [sortDir, setSortDir] = React.useState<"asc" | "desc">("asc");
  const [error, setError] = React.useState<string | null>(null);

  const sorted = React.useMemo(() => {
    const copy = [...members];
    copy.sort((a, b) => {
      const left = a[sortKey] ?? "";
      const right = b[sortKey] ?? "";
      const cmp = String(left).localeCompare(String(right));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [members, sortDir, sortKey]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir("asc");
  };

  const handleRoleChange = (member: TeamMember, role: OrgRole) => {
    setError(null);
    try {
      updateTeamMemberRole(organizationId, member.id, role);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update role");
    }
  };

  const SortIcon = sortDir === "asc" ? ArrowDownAZ : ArrowUpAZ;

  return (
    <div className="space-y-3">
      {error ? (
        <p className="text-xs text-terminal-danger" role="alert">
          {error}
        </p>
      ) : null}
      {!canManage ? (
        <p className="text-xs text-terminal-gray" role="status">
          You have read-only access to the member list.
        </p>
      ) : null}

      <div className="overflow-x-auto border border-terminal-green/30">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                  onClick={() => toggleSort("email")}
                >
                  Member
                  {sortKey === "email" ? <SortIcon size={12} aria-hidden="true" /> : null}
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                  onClick={() => toggleSort("role")}
                >
                  Role
                  {sortKey === "role" ? <SortIcon size={12} aria-hidden="true" /> : null}
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                  onClick={() => toggleSort("joinedAt")}
                >
                  Joined
                  {sortKey === "joinedAt" ? (
                    <SortIcon size={12} aria-hidden="true" />
                  ) : null}
                </button>
              </TableHead>
              <TableHead>Last active</TableHead>
              {canManage ? <TableHead>Actions</TableHead> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((member) => (
              <TableRow key={member.id}>
                <TableCell className="text-terminal-green">{member.email}</TableCell>
                <TableCell>
                  {canManage && member.role !== "owner" ? (
                    <select
                      aria-label={`Role for ${member.email}`}
                      value={member.role}
                      onChange={(event) =>
                        handleRoleChange(member, event.target.value as OrgRole)
                      }
                      className="min-h-[36px] border border-terminal-gray/40 bg-terminal-black px-2 text-xs text-terminal-green"
                    >
                      {(["admin", "operator", "viewer"] as OrgRole[]).map((role) => (
                        <option key={role} value={role}>
                          {ORG_ROLE_LABELS[role]}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-terminal-cyan">
                      {ORG_ROLE_LABELS[member.role]}
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-terminal-gray">
                  {new Date(member.joinedAt).toLocaleDateString()}
                </TableCell>
                <TableCell className="text-terminal-gray">
                  {member.lastActiveAt
                    ? new Date(member.lastActiveAt).toLocaleDateString()
                    : "—"}
                </TableCell>
                {canManage ? (
                  <TableCell>
                    {member.role === "owner" ? (
                      <span className="text-[10px] uppercase tracking-widest text-terminal-gray">
                        Protected
                      </span>
                    ) : (
                      <Button
                        type="button"
                        variant="danger"
                        size="sm"
                        onClick={() => onRequestRemove(member)}
                      >
                        Remove
                      </Button>
                    )}
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
