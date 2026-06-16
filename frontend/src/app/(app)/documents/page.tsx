"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";

import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { documentsApi } from "@/lib/api";
import { formatDate } from "@/lib/format";

export default function DocumentsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["documents", "list"],
    queryFn: () => documentsApi.listDocuments(1, 50),
  });

  const documents = data?.items ?? [];

  return (
    <Card>
      <CardContent className="p-6">
        {isLoading ? (
          <div className="space-y-3">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : documents.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No documents yet"
            description="Uploaded documents and their processing status will appear here."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Uploaded</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell className="max-w-64 truncate font-medium">
                    {doc.name}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {doc.document_type.replace(/_/g, " ")}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={doc.status} />
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {formatDate(doc.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
