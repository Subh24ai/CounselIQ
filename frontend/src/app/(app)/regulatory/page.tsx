"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Plus, Scale, Target } from "lucide-react";

import { LogUpdateDialog } from "@/components/regulatory/LogUpdateDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { regulatoryApi } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useAuthStore } from "@/store/auth";
import type { RegulatorySource, RegulatoryUpdate } from "@/types";

const SOURCES: RegulatorySource[] = [
  "SEBI",
  "IRDAI",
  "MCA",
  "RBI",
  "NABH",
  "other",
];

const PAGE_SIZE = 50;

export default function RegulatoryPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canManage = role === "org_admin" || role === "compliance_officer";

  const [source, setSource] = useState<string>("all");
  const [logOpen, setLogOpen] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["regulatory", "updates", source],
    queryFn: () =>
      regulatoryApi.listUpdates(
        1,
        PAGE_SIZE,
        source === "all" ? undefined : source,
      ),
  });

  const items = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Regulatory Monitor</h2>
          <p className="text-sm text-muted-foreground">
            Indian statutes and regulator circulars, matched to your contracts.
          </p>
        </div>
        {canManage && (
          <Button onClick={() => setLogOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Log Update
          </Button>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Select value={source} onValueChange={setSource}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All sources</SelectItem>
            {SOURCES.map((s) => (
              <SelectItem key={s} value={s}>
                {s === "other" ? "Other" : s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      ) : isError ? (
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            Couldn&apos;t load regulatory updates. Please retry.
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="p-6">
            <EmptyState
              icon={Scale}
              title="No regulatory updates yet"
              description={
                canManage
                  ? "Log a circular or statutory change to start tracking its impact on your contracts."
                  : "Regulatory updates logged by your compliance team will appear here."
              }
              action={
                canManage ? (
                  <Button onClick={() => setLogOpen(true)}>
                    <Plus className="mr-2 h-4 w-4" />
                    Log Update
                  </Button>
                ) : undefined
              }
            />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {items.map((update) => (
            <UpdateCard key={update.id} update={update} />
          ))}
        </div>
      )}

      <LogUpdateDialog open={logOpen} onOpenChange={setLogOpen} />
    </div>
  );
}

function UpdateCard({ update }: { update: RegulatoryUpdate }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{update.source ?? "other"}</Badge>
          {!update.is_processed && <Badge variant="warning">New</Badge>}
          <span className="ml-auto text-xs text-muted-foreground">
            {formatDate(update.published_date)}
          </span>
        </div>

        <Link href={`/regulatory/${update.id}`} className="block">
          <h3 className="font-semibold hover:underline">{update.title}</h3>
        </Link>

        {update.summary && (
          <div>
            <p
              className={expanded ? "text-sm" : "line-clamp-2 text-sm"}
            >
              {update.summary}
            </p>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-1 text-xs font-medium text-primary hover:underline"
            >
              {expanded ? "Show less" : "Read more"}
            </button>
          </div>
        )}

        <div className="flex justify-end">
          <Button asChild variant="outline" size="sm">
            <Link href={`/regulatory/${update.id}`}>
              <Target className="mr-2 h-4 w-4" />
              View Impact
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
