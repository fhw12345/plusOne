"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";

import { ChipInput } from "@/components/profile/ChipInput";
import { DeleteAccountDialog } from "@/components/profile/DeleteAccountDialog";
import { VisitedCitiesField } from "@/components/profile/VisitedCitiesField";
import { useExportMe } from "@/hooks/useExportMe";
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

interface SectionHeaderProps {
  caption: string;
  hint?: string;
}

function SectionHeader({ caption, hint }: SectionHeaderProps) {
  return (
    <div style={{ marginBottom: 6 }}>
      <h2 className="hand-lg" style={{ fontSize: 28, lineHeight: 1.05 }}>
        {caption}
      </h2>
      {hint ? (
        <p className="scrawl" style={{ fontSize: 14, marginTop: 2 }}>
          {hint}
        </p>
      ) : null}
    </div>
  );
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
        setServerError(err.message || "couldn't save. one more try?");
      } else {
        setServerError("couldn't save. one more try?");
      }
    }
  };

  if (isLoading) {
    return (
      <p className="scrawl" style={{ fontSize: 16 }}>
        one sec &mdash; pulling your notes&hellip;
      </p>
    );
  }
  if (isError) {
    return (
      <p role="alert" className="annot" style={{ display: "block" }}>
        couldn&rsquo;t open your page.
      </p>
    );
  }

  return (
    <>
      <form
        onSubmit={handleSubmit(onSubmit)}
        noValidate
        style={{ display: "flex", flexDirection: "column", gap: 30 }}
      >
      <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <SectionHeader
          caption="about you"
          hint="age + language. helps pace + voice."
        />
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 18,
          }}
        >
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="age_range">age range</label>
            <input
              id="age_range"
              maxLength={20}
              placeholder="e.g. 30-39"
              {...register("demographics.age_range", {
                setValueAs: (v) => (v === "" ? null : v),
              })}
            />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="language">first language</label>
            <input
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

      <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <SectionHeader
          caption="how you travel"
          hint="rough strokes &mdash; budget, pace, comfort."
        />
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr",
            gap: 18,
          }}
        >
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="budget_sensitivity">budget</label>
            <input
              id="budget_sensitivity"
              maxLength={20}
              placeholder="e.g. moderate"
              {...register("travel_style.budget_sensitivity", {
                setValueAs: (v) => (v === "" ? null : v),
              })}
            />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="pace">pace</label>
            <input
              id="pace"
              maxLength={20}
              placeholder="e.g. relaxed"
              {...register("travel_style.pace", {
                setValueAs: (v) => (v === "" ? null : v),
              })}
            />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="comfort">comfort</label>
            <input
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

      <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <SectionHeader
          caption="loves &amp; dealbreakers"
          hint="hit enter after each one. the dealbreakers go further than the loves."
        />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>loves</label>
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
          <div className="field" style={{ marginBottom: 0 }}>
            <label>dealbreakers</label>
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

      <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <SectionHeader
          caption="been there"
          hint="cities you've already done. i'll soften repeats."
        />
        <Controller
          control={control}
          name="visited_cities"
          render={({ field }) => (
            <VisitedCitiesField value={field.value} onChange={field.onChange} />
          )}
        />
      </section>

      <div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 8 }}>
        <button
          type="submit"
          disabled={isSubmitting || mutation.isPending}
          className="btn btn--red"
          style={{ opacity: isSubmitting || mutation.isPending ? 0.55 : 1 }}
        >
          {isSubmitting || mutation.isPending ? "pinning…" : "pin it"}
        </button>
        {saved ? (
          <span
            role="status"
            className="annot"
            style={{ display: "inline-block", fontSize: 16 }}
          >
            pinned ★
          </span>
        ) : null}
        {serverError ? (
          <span
            role="alert"
            className="annot"
            style={{ display: "inline-block" }}
          >
            {serverError}
          </span>
        ) : null}
      </div>
    </form>

      <ExportDataSection />
      <DangerZoneSection />
    </>
  );
}

function ExportDataSection() {
  const exportMut = useExportMe();
  const failed = exportMut.isError;

  return (
    <section
      style={{
        position: "relative",
        marginTop: 36,
        padding: "24px 28px 28px",
        background: "hsl(var(--paper-2))",
        border: "1px solid hsl(var(--kraft))",
        boxShadow: "0 10px 20px -16px hsl(0 0% 0% / .2)",
      }}
    >
      <span
        className="tape tape--mint"
        style={{ top: -10, left: 28, width: 96, height: 22, transform: "rotate(-3deg)" }}
      />
      <h2 className="hand-lg" style={{ fontSize: 28, lineHeight: 1.05 }}>
        your data
      </h2>
      <p className="scrawl" style={{ fontSize: 14, marginTop: 2 }}>
        everything you&rsquo;ve pinned, packed up. one click.
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 14 }}>
        <button
          type="button"
          className="btn"
          data-testid="export-data-button"
          disabled={exportMut.isPending}
          onClick={() => exportMut.mutate()}
          style={{ opacity: exportMut.isPending ? 0.55 : 1 }}
        >
          {exportMut.isPending ? "packing…" : "download my data"}
        </button>
        {failed ? (
          <span role="alert" className="annot" style={{ display: "inline-block" }}>
            couldn&rsquo;t pack it up. one more try?
          </span>
        ) : null}
      </div>
    </section>
  );
}

function DangerZoneSection() {
  return (
    <section
      style={{
        position: "relative",
        marginTop: 32,
        padding: "24px 28px 28px",
        background: "hsl(var(--paper-2))",
        border: "1px solid hsl(0 70% 40% / .55)",
        boxShadow: "0 10px 20px -16px hsl(0 0% 0% / .2)",
      }}
    >
      <span
        className="tape tape--red"
        style={{ top: -10, left: 28, width: 96, height: 22, transform: "rotate(3deg)" }}
      />
      <h2 className="hand-lg" style={{ fontSize: 28, lineHeight: 1.05 }}>
        the page goes
      </h2>
      <p className="scrawl" style={{ fontSize: 14, marginTop: 2 }}>
        this clears everything. no putting it back.
      </p>
      <div style={{ marginTop: 14 }}>
        <DeleteAccountDialog />
      </div>
    </section>
  );
}
