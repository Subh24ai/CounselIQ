"use client";

import { Scale } from "lucide-react";

import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent } from "@/components/ui/card";

export default function RegulatoryPage() {
  return (
    <Card>
      <CardContent className="p-6">
        <EmptyState
          icon={Scale}
          title="Regulatory monitoring"
          description="Track changes to Indian statutes and regulator circulars relevant to your contracts. Compliance officers will see new regulatory updates and affected documents here."
        />
      </CardContent>
    </Card>
  );
}
