"use client";

import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useDropzone, type FileRejection } from "react-dropzone";
import { FileText, Loader2, UploadCloud, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { documentsApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui";
import type { DocumentType } from "@/types";

const MAX_SIZE = 50 * 1024 * 1024; // 50 MB

const ACCEPT = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
    ".docx",
  ],
  "text/plain": [".txt"],
};

const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: "vendor_contract", label: "Vendor Contract" },
  { value: "employment", label: "Employment Agreement" },
  { value: "nda", label: "NDA" },
  { value: "msa", label: "Master Service Agreement" },
  { value: "policy", label: "Policy" },
  { value: "regulatory", label: "Regulatory Filing" },
  { value: "other", label: "Other" },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function UploadDialog({ open, onOpenChange }: UploadDialogProps) {
  const queryClient = useQueryClient();
  const notify = useUIStore((s) => s.addNotification);

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [docType, setDocType] = useState<DocumentType>("vendor_contract");
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setFile(null);
    setName("");
    setDocType("vendor_contract");
    setProgress(0);
    setUploading(false);
    setFormError(null);
  }, []);

  // Reset internal state whenever the dialog is closed.
  useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  const onDrop = useCallback(
    (accepted: File[]) => {
      const dropped = accepted[0];
      if (!dropped) return;
      setFile(dropped);
      // Auto-fill the name from the filename (without extension) if empty.
      if (!name) {
        setName(dropped.name.replace(/\.[^./]+$/, ""));
      }
      setFormError(null);
    },
    [name],
  );

  const onDropRejected = useCallback(
    (rejections: FileRejection[]) => {
      const error = rejections[0]?.errors[0];
      if (error?.code === "file-too-large") {
        notify({ type: "error", message: "File exceeds the 50 MB limit." });
      } else if (error?.code === "file-invalid-type") {
        notify({
          type: "error",
          message: "Unsupported file type. Upload a PDF, DOCX, or TXT file.",
        });
      } else {
        notify({ type: "error", message: error?.message ?? "File rejected." });
      }
    },
    [notify],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected,
    accept: ACCEPT,
    maxSize: MAX_SIZE,
    multiple: false,
    disabled: uploading,
  });

  async function handleUpload() {
    if (!file) {
      setFormError("Please choose a file to upload.");
      return;
    }
    if (!name.trim()) {
      setFormError("Please give the document a name.");
      return;
    }

    setFormError(null);
    setUploading(true);
    setProgress(0);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", name.trim());
    formData.append("document_type", docType);

    try {
      await documentsApi.uploadDocument(formData, setProgress);
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      notify({ type: "success", message: `"${name.trim()}" uploaded.` });
      onOpenChange(false);
    } catch (error) {
      setUploading(false);
      notify({ type: "error", message: getApiErrorMessage(error) });
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !uploading && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload Document</DialogTitle>
          <DialogDescription>
            PDF, DOCX, or TXT up to 50 MB. Extraction starts automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {!file ? (
            <div
              {...getRootProps()}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
                isDragActive
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50",
              )}
            >
              <input {...getInputProps()} />
              <UploadCloud className="mb-3 h-8 w-8 text-muted-foreground" />
              <p className="text-sm font-medium">
                {isDragActive
                  ? "Drop the file here"
                  : "Drag & drop a file, or click to browse"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                PDF, DOCX, or TXT · max 50 MB
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded-lg border p-3">
              <FileText className="h-8 w-8 shrink-0 text-primary" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(file.size)}
                </p>
              </div>
              {!uploading && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setFile(null)}
                  aria-label="Remove file"
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="doc-name">Name</Label>
            <Input
              id="doc-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Acme Vendor Agreement 2026"
              disabled={uploading}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="doc-type">Document type</Label>
            <Select
              value={docType}
              onValueChange={(v) => setDocType(v as DocumentType)}
              disabled={uploading}
            >
              <SelectTrigger id="doc-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DOCUMENT_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {uploading && (
            <div className="space-y-1">
              <Progress value={progress} />
              <p className="text-right text-xs text-muted-foreground">
                {progress}%
              </p>
            </div>
          )}

          {formError && (
            <p className="text-sm text-destructive">{formError}</p>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={uploading}
          >
            Cancel
          </Button>
          <Button onClick={handleUpload} disabled={uploading || !file}>
            {uploading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {uploading ? "Uploading…" : "Upload"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
