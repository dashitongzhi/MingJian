import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ColumnDef } from "@tanstack/react-table";
import { describe, expect, it, vi } from "vitest";
import { DataTable } from "@/components/ui/data-table";

type Person = {
  name: string;
  role: string;
};

const columns: ColumnDef<Person>[] = [
  {
    accessorKey: "name",
    header: "Name",
  },
  {
    accessorKey: "role",
    header: "Role",
  },
];

const data: Person[] = [
  { name: "Ada Lovelace", role: "Analyst" },
  { name: "Grace Hopper", role: "Engineer" },
  { name: "Katherine Johnson", role: "Navigator" },
];

describe("DataTable", () => {
  it("renders column headers and data rows", () => {
    render(<DataTable columns={columns} data={data} />);

    expect(screen.getByRole("columnheader", { name: /name/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /role/i })).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Grace Hopper")).toBeInTheDocument();
    expect(screen.getByText("Katherine Johnson")).toBeInTheDocument();
  });

  it('shows "暂无数据" when there are no rows', () => {
    render(<DataTable columns={columns} data={[]} />);

    expect(screen.getByText("暂无数据")).toBeInTheDocument();
    expect(screen.getByText("共 0 条记录")).toBeInTheDocument();
  });

  it("filters rows with the configured search column", () => {
    render(
      <DataTable
        columns={columns}
        data={data}
        searchColumn="name"
        searchPlaceholder="Search names"
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("Search names"), {
      target: { value: "Grace" },
    });

    expect(screen.getByText("Grace Hopper")).toBeInTheDocument();
    expect(screen.queryByText("Ada Lovelace")).not.toBeInTheDocument();
    expect(screen.queryByText("Katherine Johnson")).not.toBeInTheDocument();
    expect(screen.getByText("共 1 条记录")).toBeInTheDocument();
  });

  it("calls onRowClick with the original row data", () => {
    const handleRowClick = vi.fn();
    render(<DataTable columns={columns} data={data} onRowClick={handleRowClick} />);

    fireEvent.click(within(screen.getByText("Ada Lovelace").closest("tr")!).getByText("Ada Lovelace"));

    expect(handleRowClick).toHaveBeenCalledWith(data[0]);
  });
});
