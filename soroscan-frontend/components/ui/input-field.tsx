"use client"

import * as React from "react"

import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export type InputFieldProps = Omit<
  React.ComponentProps<typeof Input>,
  "id" | "aria-describedby" | "aria-invalid" | "aria-errormessage" | "ref"
> & {
  /** Visible label; linked to the control via `htmlFor` / `id`. */
  label?: React.ReactNode
  /** Stable id for the input (also used for hint/error ids). */
  id?: string
  /** When a string, message is shown and the field is marked invalid. */
  error?: string | boolean
  /** Helper text shown when there is no error message. */
  hint?: React.ReactNode
  labelClassName?: string
  hintClassName?: string
  errorClassName?: string
  containerClassName?: string
}

/**
 * Input with optional label, hint, and validation error region.
 * Wires `aria-invalid`, `aria-describedby`, and `role="alert"` for errors.
 */
const InputField = React.forwardRef<HTMLInputElement, InputFieldProps>(
  function InputField(
    {
      label,
      id: idProp,
      error,
      hint,
      className,
      labelClassName,
      hintClassName,
      errorClassName,
      containerClassName,
      ...inputProps
    },
    ref
  ) {
  const generatedId = React.useId()
  const id = idProp ?? generatedId
  const hintId = `${id}-hint`
  const errorId = `${id}-error`

  const errorMessage = typeof error === "string" ? error : ""
  const hasError = Boolean(error)
  const showErrorMessage = Boolean(errorMessage)

  const describedBy = [
    hint && !hasError ? hintId : null,
    showErrorMessage ? errorId : null,
  ]
    .filter(Boolean)
    .join(" ")

  return (
    <div
      data-slot="input-field"
      className={cn("grid gap-2", containerClassName)}
    >
      {label !== undefined && label !== null ? (
        <Label htmlFor={id} className={labelClassName}>
          {label}
        </Label>
      ) : null}
      <Input
        ref={ref}
        id={id}
        aria-invalid={hasError ? true : undefined}
        aria-errormessage={showErrorMessage ? errorId : undefined}
        aria-describedby={describedBy || undefined}
        className={className}
        {...inputProps}
      />
      {hint !== undefined && hint !== null && !hasError ? (
        <p
          id={hintId}
          data-slot="input-field-hint"
          className={cn("text-muted-foreground text-sm", hintClassName)}
        >
          {hint}
        </p>
      ) : null}
      {showErrorMessage ? (
        <p
          id={errorId}
          role="alert"
          data-slot="input-field-error"
          className={cn("text-destructive text-sm", errorClassName)}
        >
          {errorMessage}
        </p>
      ) : null}
    </div>
  )
  }
)

InputField.displayName = "InputField"

export { InputField }
