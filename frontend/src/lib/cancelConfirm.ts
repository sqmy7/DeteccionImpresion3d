/** Cancelling a print cannot be undone, so the web asks twice: a first confirmation, and then the word
 * below typed out. The server requires the same word (app/api/v1/printers.py, CancelRequest). */
export const CANCEL_WORD = "CANCELAR";

/** True only for the exact word (surrounding spaces are forgiven; lower case or another word are not). */
export function isCancelConfirmed(typed: string): boolean {
  return typed.trim() === CANCEL_WORD;
}
