"use client";

import { useCallback, useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { regulatoryApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { useUIStore } from "@/store/ui";
import type { RegulatorySource } from "@/types";

const SOURCES: RegulatorySource[] = [
  "SEBI",
  "IRDAI",
  "MCA",
  "RBI",
  "NABH",
  "other",
];

export interface LogUpdateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function LogUpdateDialog({ open, onOpenChange }: LogUpdateDialogProps) {
  const queryClient = useQueryClient();
  const notify = useUIStore((s) => s.addNotification);

  const [source, setSource] = useState<string>("SEBI");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [fullText, setFullText] = useState("");
  const [url, setUrl] = useState("");
  const [publishedDate, setPublishedDate] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setSource("SEBI");
    setTitle("");
    setSummary("");
    setFullText("");
    setUrl("");
    setPublishedDate("");
    setFormError(null);
  }, []);

  useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  const createMutation = useMutation({
    mutationFn: () =>
      regulatoryApi.createUpdate({
        source,
        title: title.trim(),
        summary: summary.trim(),
        full_text: fullText.trim() || null,
        url: url.trim() || null,
        published_date: publishedDate,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["regulatory"] });
      notify({ type: "success", message: "Regulatory update logged." });
      onOpenChange(false);
    },
    onError: (error) => {
      notify({ type: "error", message: getApiErrorMessage(error) });
    },
  });

  function handleSubmit() {
    if (!title.trim() || !summary.trim() || !publishedDate) {
      setFormError("Title, summary, and published date are required.");
      return;
    }
    setFormError(null);
    createMutation.mutate();
  }

  const pending = createMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Log Regulatory Update</DialogTitle>
          <DialogDescription>
            Record a circular or statutory change. It will be embedded and
            matched against your contracts.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="reg-source">Source</Label>
              <Select
                value={source}
                onValueChange={setSource}
                disabled={pending}
              >
                <SelectTrigger id="reg-source">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SOURCES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s === "other" ? "Other" : s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="reg-date">Published date</Label>
              <Input
                id="reg-date"
                type="date"
                value={publishedDate}
                onChange={(e) => setPublishedDate(e.target.value)}
                disabled={pending}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="reg-title">Title</Label>
            <Input
              id="reg-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. SEBI LODR amendment — related-party transactions"
              disabled={pending}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="reg-summary">Summary</Label>
            <Textarea
              id="reg-summary"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="What changed and what it affects…"
              disabled={pending}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="reg-fulltext">Full text (optional)</Label>
            <Textarea
              id="reg-fulltext"
              value={fullText}
              onChange={(e) => setFullText(e.target.value)}
              placeholder="Paste the full circular text if available…"
              disabled={pending}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="reg-url">Source URL (optional)</Label>
            <Input
              id="reg-url"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.sebi.gov.in/…"
              disabled={pending}
            />
          </div>

          {formError && <p className="text-sm text-destructive">{formError}</p>}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={pending}>
            {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {pending ? "Saving…" : "Log Update"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
