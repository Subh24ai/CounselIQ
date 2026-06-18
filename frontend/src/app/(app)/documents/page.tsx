"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Brain,
  FileText,
  Loader2,
  Plus,
  Search,
  Trash2,
} from "lucide-react";

import { AnalyseDialog } from "@/components/documents/AnalyseDialog";
import { UploadDialog } from "@/components/documents/UploadDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { isAnalysableStatus } from "@/lib/analysis";
import { documentsApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import { useAuthStore } from "@/store/auth";
import { useUIStore } from "@/store/ui";
import type { Document, DocumentStatus, DocumentType } from "@/types";

const PAGE_SIZE = 20;
const POLL_STATUSES: DocumentStatus[] = ["queued", "extracting", "analysing"];

const STATUS_OPTIONS: DocumentStatus[] = [
  "uploaded",
  "queued",
  "extracting",
  "extracted",
  "analysing",
  "completed",
  "failed",
  "deleted",
];

const TYPE_OPTIONS: DocumentType[] = [
  "vendor_contract",
  "employment",
  "nda",
  "msa",
  "policy",
  "regulatory",
  "other",
];

function humanize(value: string): string {
  return value
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export default function DocumentsPage() {
  const queryClient = useQueryClient();
  const notify = useUIStore((s) => s.addNotification);
  const currentUserId = useAuthStore((s) => s.user?.id);

  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [showDeleted, setShowDeleted] = useState(false);

  // The backend excludes soft-deleted documents by default. Pull them in when
  // the "Show deleted" toggle is on, or when the user explicitly filters by the
  // "Deleted" status (otherwise that filter would always be empty).
  const includeDeleted = showDeleted || statusFilter === "deleted";

  const [uploadOpen, setUploadOpen] = useState(false);
  const [analyseTarget, setAnalyseTarget] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Document | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["documents", "list", page, includeDeleted],
    queryFn: () => documentsApi.listDocuments(page, PAGE_SIZE, includeDeleted),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some((d) => POLL_STATUSES.includes(d.status)) ? 5000 : false;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => documentsApi.deleteDocument(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      notify({ type: "success", message: "Document deleted." });
      setDeleteTarget(null);
    },
    onError: (error) => {
      notify({ type: "error", message: getApiErrorMessage(error) });
    },
  });

  const filtered = useMemo(() => {
    const items = data?.items ?? [];
    const term = search.trim().toLowerCase();
    return items.filter((doc) => {
      if (statusFilter !== "all" && doc.status !== statusFilter) return false;
      if (typeFilter !== "all" && doc.document_type !== typeFilter) return false;
      if (term && !doc.name.toLowerCase().includes(term)) return false;
      return true;
    });
  }, [data?.items, statusFilter, typeFilter, search]);

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function uploadedByLabel(doc: Document): string {
    if (!doc.uploaded_by) return "—";
    if (doc.uploaded_by === currentUserId) return "You";
    return doc.uploaded_by.slice(0, 8);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Documents</h2>
          <p className="text-sm text-muted-foreground">
            Upload contracts and track extraction status.
          </p>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Upload Document
        </Button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name…"
            className="pl-9"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="sm:w-44">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {humanize(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="sm:w-48">
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {TYPE_OPTIONS.map((t) => (
              <SelectItem key={t} value={t}>
                {humanize(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          variant={showDeleted ? "secondary" : "outline"}
          onClick={() => {
            setShowDeleted((v) => !v);
            setPage(1);
          }}
          aria-pressed={showDeleted}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          {showDeleted ? "Hide deleted" : "Show deleted"}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-3 p-6">
              {[0, 1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : isError ? (
            <div className="p-6 text-sm text-destructive">
              Couldn&apos;t load documents. Please retry.
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={FileText}
                title={
                  (data?.items.length ?? 0) === 0
                    ? "No documents yet"
                    : "No matching documents"
                }
                description={
                  (data?.items.length ?? 0) === 0
                    ? "Upload your first contract to begin compliance analysis."
                    : "Try adjusting your filters or search term."
                }
                action={
                  (data?.items.length ?? 0) === 0 ? (
                    <Button onClick={() => setUploadOpen(true)}>
                      <Plus className="mr-2 h-4 w-4" />
                      Upload Document
                    </Button>
                  ) : undefined
                }
              />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Pages</TableHead>
                  <TableHead>Uploaded By</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((doc) => (
                  <TableRow key={doc.id}>
                    <TableCell className="max-w-56 truncate font-medium">
                      <Link
                        href={`/documents/${doc.id}`}
                        className="hover:underline"
                      >
                        {doc.name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {humanize(doc.document_type)}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={doc.status} />
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {doc.page_count ?? "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {uploadedByLabel(doc)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(doc.created_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="sm" asChild>
                          <Link href={`/documents/${doc.id}`}>View</Link>
                        </Button>
                        {isAnalysableStatus(doc.status) && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setAnalyseTarget(doc.id)}
                          >
                            <Brain className="mr-1 h-4 w-4" />
                            Analyse
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setDeleteTarget(doc)}
                          aria-label="Delete document"
                        >
                          <Trash2 className="h-4 w-4 text-muted-foreground" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {page} of {totalPages} · {total} documents
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      <AnalyseDialog
        open={analyseTarget !== null}
        onOpenChange={(open) => !open && setAnalyseTarget(null)}
        documentId={analyseTarget}
      />

      {/* Delete confirmation */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete document?</DialogTitle>
            <DialogDescription>
              &ldquo;{deleteTarget?.name}&rdquo; will be removed. This cannot be
              undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() =>
                deleteTarget && deleteMutation.mutate(deleteTarget.id)
              }
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
