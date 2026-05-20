"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { CompanionResponse } from "@/lib/schemas/companions";

interface CompanionCardProps {
  companion: CompanionResponse;
  onEdit: (companion: CompanionResponse) => void;
  onDelete: (companion: CompanionResponse) => void;
}

const TOP = 3;

function topChips(items: readonly string[]): { shown: string[]; extra: number } {
  return { shown: items.slice(0, TOP), extra: Math.max(0, items.length - TOP) };
}

export function CompanionCard({ companion, onEdit, onDelete }: CompanionCardProps) {
  const loves = topChips(companion.explicit_preferences.loves);
  const hates = topChips(companion.explicit_preferences.hates);
  const { dietary } = companion.constraints;
  const dietaryTop = topChips(dietary);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>{companion.name}</CardTitle>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onEdit(companion)}
            aria-label={`Edit ${companion.name}`}
          >
            Edit
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onDelete(companion)}
            aria-label={`Delete ${companion.name}`}
            className="text-red-600 hover:bg-red-50"
          >
            Delete
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {loves.shown.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-foreground/60 mr-1 text-xs">Loves:</span>
            {loves.shown.map((v) => (
              <Badge key={`loves-${v}`} variant="success">
                {v}
              </Badge>
            ))}
            {loves.extra > 0 ? (
              <span className="text-foreground/60 text-xs">+{loves.extra}</span>
            ) : null}
          </div>
        ) : null}
        {hates.shown.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-foreground/60 mr-1 text-xs">Hates:</span>
            {hates.shown.map((v) => (
              <Badge key={`hates-${v}`} variant="danger">
                {v}
              </Badge>
            ))}
            {hates.extra > 0 ? (
              <span className="text-foreground/60 text-xs">+{hates.extra}</span>
            ) : null}
          </div>
        ) : null}
        {dietaryTop.shown.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-foreground/60 mr-1 text-xs">Dietary:</span>
            {dietaryTop.shown.map((v) => (
              <Badge key={`diet-${v}`} variant="secondary">
                {v}
              </Badge>
            ))}
            {dietaryTop.extra > 0 ? (
              <span className="text-foreground/60 text-xs">+{dietaryTop.extra}</span>
            ) : null}
          </div>
        ) : null}
        {companion.constraints.mobility || companion.constraints.max_walking != null ? (
          <p className="text-foreground/60 text-xs">
            {companion.constraints.mobility ? `Mobility: ${companion.constraints.mobility}` : null}
            {companion.constraints.mobility && companion.constraints.max_walking != null
              ? " · "
              : ""}
            {companion.constraints.max_walking != null
              ? `Max walking: ${companion.constraints.max_walking} km/day`
              : null}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
