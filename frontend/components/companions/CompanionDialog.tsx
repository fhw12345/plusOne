"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";

import { ChipInput } from "@/components/profile/ChipInput";
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
import { useCreateCompanion, useUpdateCompanion } from "@/hooks/useCompanions";
import { CompanionConflictError } from "@/lib/api/companions";
import { ApiError } from "@/lib/api/client";
import {
  CompanionCreateBody,
  type CompanionCreateBody as CompanionCreateBodyT,
  type CompanionResponse,
} from "@/lib/schemas/companions";

interface CompanionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Companion to edit; undefined = create-new */
  companion?: CompanionResponse;
}

const EMPTY: CompanionCreateBodyT = {
  name: "",
  explicit_preferences: { loves: [], hates: [] },
  constraints: { dietary: [], mobility: null, max_walking: null },
};

function toFormValues(c: CompanionResponse | undefined): CompanionCreateBodyT {
  if (!c) return EMPTY;
  return {
    name: c.name,
    explicit_preferences: {
      loves: [...c.explicit_preferences.loves],
      hates: [...c.explicit_preferences.hates],
    },
    constraints: {
      dietary: [...c.constraints.dietary],
      mobility: c.constraints.mobility ?? null,
      max_walking: c.constraints.max_walking ?? null,
    },
  };
}

/**
 * Outer dialog. When `open` flips true, we render a fresh `<CompanionForm>`
 * instance so RHF's defaultValues + local error state are reset implicitly
 * (no effect needed). When closed, the inner form unmounts entirely.
 */
export function CompanionDialog({ open, onOpenChange, companion }: CompanionDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{companion ? "Edit companion" : "Add companion"}</DialogTitle>
          <DialogDescription>
            Their loves, hates, and constraints feed into the trip plan.
          </DialogDescription>
        </DialogHeader>
        {open ? (
          <CompanionForm
            companion={companion}
            onCancel={() => onOpenChange(false)}
            onSaved={() => onOpenChange(false)}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

interface CompanionFormProps {
  companion?: CompanionResponse;
  onCancel: () => void;
  onSaved: () => void;
}

function CompanionForm({ companion, onCancel, onSaved }: CompanionFormProps) {
  const isEdit = !!companion;
  const create = useCreateCompanion();
  const update = useUpdateCompanion();
  const [nameError, setNameError] = React.useState<string | null>(null);
  const [serverError, setServerError] = React.useState<string | null>(null);

  const {
    control,
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CompanionCreateBodyT>({
    resolver: zodResolver(CompanionCreateBody),
    defaultValues: toFormValues(companion),
  });

  const onSubmit = async (values: CompanionCreateBodyT) => {
    setNameError(null);
    setServerError(null);
    try {
      if (isEdit && companion) {
        await update.mutateAsync({ id: companion.id, body: values });
      } else {
        await create.mutateAsync(values);
      }
      onSaved();
    } catch (err) {
      if (err instanceof CompanionConflictError) {
        if (err.kind === "companion_name_taken") {
          setNameError("Name already taken — pick another.");
          return;
        }
        if (err.kind === "companion_limit_reached") {
          setServerError("You've reached the 20-companion limit.");
          return;
        }
      }
      if (err instanceof ApiError) {
        setServerError(err.message || "Couldn't save companion. Please try again.");
      } else {
        setServerError("Couldn't save companion. Please try again.");
      }
    }
  };

  const pending = isSubmitting || create.isPending || update.isPending;

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      <div className="flex flex-col gap-1">
        <Label htmlFor="companion-name">Name</Label>
        <Input
          id="companion-name"
          {...register("name")}
          aria-invalid={errors.name || nameError ? "true" : "false"}
          maxLength={100}
          autoFocus
        />
        {errors.name ? (
          <span role="alert" className="text-sm text-red-600">
            {errors.name.message}
          </span>
        ) : null}
        {nameError ? (
          <span role="alert" className="text-sm text-red-600">
            {nameError}
          </span>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <Label>Loves</Label>
          <Controller
            control={control}
            name="explicit_preferences.loves"
            render={({ field }) => (
              <ChipInput
                value={field.value}
                onChange={field.onChange}
                ariaLabel="Loves"
                placeholder="e.g. matcha"
              />
            )}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Hates</Label>
          <Controller
            control={control}
            name="explicit_preferences.hates"
            render={({ field }) => (
              <ChipInput
                value={field.value}
                onChange={field.onChange}
                ariaLabel="Hates"
                placeholder="e.g. seafood"
              />
            )}
          />
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <Label>Dietary</Label>
        <Controller
          control={control}
          name="constraints.dietary"
          render={({ field }) => (
            <ChipInput
              value={field.value}
              onChange={field.onChange}
              ariaLabel="Dietary"
              placeholder="e.g. vegetarian"
              max={20}
            />
          )}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor="companion-mobility">Mobility</Label>
          <Input
            id="companion-mobility"
            maxLength={50}
            placeholder="e.g. limited stairs"
            {...register("constraints.mobility", {
              setValueAs: (v) => (v === "" ? null : v),
            })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="companion-max-walking">Max walking (km/day)</Label>
          <Input
            id="companion-max-walking"
            type="number"
            min={0}
            max={100}
            {...register("constraints.max_walking", {
              setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
            })}
          />
        </div>
      </div>

      {serverError ? (
        <p role="alert" className="text-sm text-red-600">
          {serverError}
        </p>
      ) : null}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : isEdit ? "Save" : "Add"}
        </Button>
      </DialogFooter>
    </form>
  );
}
