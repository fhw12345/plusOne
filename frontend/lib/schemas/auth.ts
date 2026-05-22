import { z } from "zod";

// Reusable email schema — voice copy lives in the inline error rules.
export const EmailSchema = z
  .string()
  .email("that email doesn't look right. typo?");

// Username: lowercase letters, digits, and underscores. 3 to 32 chars.
// Backend enforces the same shape on POST /api/auth/register.
export const UsernameSchema = z
  .string()
  .regex(
    /^[a-z0-9_]{3,32}$/,
    "username's lowercase, letters and numbers, three to thirty-two.",
  );

// Password: min 10, at least one letter + one digit.
export const PasswordSchema = z
  .string()
  .min(10, "password needs ten characters and a number. one more pass?")
  .regex(
    /[A-Za-z]/,
    "password needs ten characters and a number. one more pass?",
  )
  .regex(/\d/, "password needs ten characters and a number. one more pass?");

// Six-digit verification / login code.
export const CodeSchema = z
  .string()
  .regex(/^\d{6}$/, "just the numbers. all six of them.");

export const RegisterBody = z
  .object({
    username: UsernameSchema,
    email: EmailSchema,
    password: PasswordSchema,
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    path: ["confirm"],
    message: "those don't match. one more look?",
  });
export type RegisterBody = z.infer<typeof RegisterBody>;

export const VerifyBody = z.object({
  email: EmailSchema,
  code: CodeSchema,
});
export type VerifyBody = z.infer<typeof VerifyBody>;

export const LoginBody = z.object({
  identifier: z
    .string()
    .min(1, "tell me who you are first.")
    .max(254),
  password: z.string().min(1, "password too. then we go."),
});
export type LoginBody = z.infer<typeof LoginBody>;

export const RequestCodeBody = z.object({
  email: EmailSchema,
});
export type RequestCodeBody = z.infer<typeof RequestCodeBody>;

export const LoginWithCodeBody = z.object({
  email: EmailSchema,
  code: CodeSchema,
});
export type LoginWithCodeBody = z.infer<typeof LoginWithCodeBody>;

// Extended User shape: includes username + is_admin (added in batch-2m).
export const UserSchema = z.object({
  id: z.string().min(1),
  email: z.string().email(),
  username: z.string(),
  is_admin: z.boolean(),
});
export type UserSchema = z.infer<typeof UserSchema>;

export const TokenResponse = z.object({
  access_token: z.string(),
  token_type: z.literal("bearer"),
  expires_in_minutes: z.number().int().positive(),
  user: UserSchema,
});
export type TokenResponse = z.infer<typeof TokenResponse>;

export const RegisterResponse = z.object({
  user_id: z.string().min(1),
  email: z.string().email(),
});
export type RegisterResponse = z.infer<typeof RegisterResponse>;

// `me` returns the same User shape as the token responses.
export const MeResponse = UserSchema;
export type MeResponse = z.infer<typeof MeResponse>;
