"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";

import { ChipInput } from "@/components/profile/ChipInput";
import { VisitedCitiesField } from "@/components/profile/VisitedCitiesField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useProfile, useUpdateProfile } from "@/hooks/useProfile";
import { ApiError } from "@/lib/api/client";
import {
  ProfileUpdateBody,
  type ProfileResponse,
  type ProfileUpdateBody as ProfileUpdateBodyT,
} from "@/lib/schemas/profile";

const EMPTY: ProfileUpdateBodyT = {
  demographics: { age_range: null, language: null },
  travel_style: { budget_sensitivity: null, pace: null, comfort: null },
  explicit_preferences: { loves: [], hates: [] },
  visited_cities: [],
};

function toFormValues(profile: ProfileResponse | undefined): ProfileUpdateBodyT {
  if (!profile) return EMPTY;
  return {
    demographics: {
      age_range: profile.demographics.age_range ?? null,
      language: profile.demographics.language ?? null,
    },
    travel_style: {
      budget_sensitivity: profile.travel_style.budget_sensitivity ?? null,
      pace: profile.travel_style.pace ?? null,
      comfort: profile.travel_style.comfort ?? null,
    },
    explicit_preferences: {
      loves: [...profile.explicit_preferences.loves],
      hates: [...profile.explicit_preferences.hates],
    },
    visited_cities: profile.visited_cities.map((v) => ({ ...v })),
  };
}

export function ProfileForm() {
  const { data: profile, isLoading, isError } = useProfile();
  const mutation = useUpdateProfile();
  const [saved, setSaved] = React.useState(false);
  const [serverError, setServerError] = React.useState<string | null>(null);

  const {
    control,
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting },
  } = useForm<ProfileUpdateBodyT>({
    resolver: zodResolver(ProfileUpdateBody),
    defaultValues: EMPTY,
  });

  // Once profile loads, hydrate the form. Use the React Query data as
  // source-of-truth (subsequent invalidations after PUT will re-trigger).
  React.useEffect(() => {
    if (profile) reset(toFormValues(profile));
  }, [profile, reset]);

  const onSubmit = async (values: ProfileUpdateBodyT) => {
    setServerError(null);
    setSaved(false);
    try {
      await mutation.mutateAsync(values);
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(err.message || "Couldn't save profile. Please try again.");
      } else {
        setServerError("Couldn't save profile. Please try again.");
      }
    }
  };

  if (isLoading) {
    return <p className="text-foreground/60 text-sm">Loading profile…</p>;
  }
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Couldn&apos;t load your profile.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-6" noValidate>
      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">Demographics</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="age_range">Age range</Label>
            <Input
              id="age_range"
              maxLength={20}
              placeholder="e.g. 30-39"
              {...register("demographics.age_range", {
                setValueAs: (v) => (v === "" ? null : v),
              })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="language">Preferred language</Label>
            <Input
              id="language"
              maxLength={10}
              placeholder="e.g. en"
              {...register("demographics.language", {
                setValueAs: (v) => (v === "" ? null : v),
              })}
            />
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">Travel style</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="budget_sensitivity">Budget sensitivity</Label>
            <Input
              id="budget_sensitivity"
              maxLength={20}
              placeholder="e.g. moderate"
              {...register("travel_style.budget_sensitivity", {
                setValueAs: (v) => (v === "" ? null : v),
              })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="pace">Pace</Label>
            <Input
              id="pace"
              maxLength={20}
              placeholder="e.g. relaxed"
              {...register("travel_style.pace", {
                setValueAs: (v) => (v === "" ? null : v),
              })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="comfort">Comfort</Label>
            <Input
              id="comfort"
              maxLength={20}
              placeholder="e.g. mid-range"
              {...register("travel_style.comfort", {
                setValueAs: (v) => (v === "" ? null : v),
              })}
            />
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">Loves & hates</h2>
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
                  placeholder="e.g. ramen"
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
                  placeholder="e.g. crowds"
                />
              )}
            />
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">Visited cities</h2>
        <Controller
          control={control}
          name="visited_cities"
          render={({ field }) => (
            <VisitedCitiesField value={field.value} onChange={field.onChange} />
          )}
        />
      </section>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={isSubmitting || mutation.isPending}>
          {isSubmitting || mutation.isPending ? "Saving…" : "Save profile"}
        </Button>
        {saved ? (
          <span role="status" className="text-sm text-emerald-600">
            Saved
          </span>
        ) : null}
        {serverError ? (
          <span role="alert" className="text-sm text-red-600">
            {serverError}
          </span>
        ) : null}
      </div>
    </form>
  );
}
