import { useState, type FormEvent } from 'react'
import { api, clearSession } from './api'

export function AccountSecurity({
  token,
  onClose,
}: {
  token: string
  onClose: () => void
}) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const form = new FormData(event.currentTarget)
    if (form.get('new_password') !== form.get('confirm_password')) {
      setError('New passwords must match.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await api('/auth/password', token, {
        method: 'POST',
        body: JSON.stringify({
          current_password: form.get('current_password'),
          new_password: form.get('new_password'),
        }),
      })
      clearSession()
      window.location.assign('/')
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Password could not be changed.',
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="modal-backdrop">
      <section
        className="form-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="security-title"
      >
        <h2 id="security-title">Change password</h2>
        <p>Changing your password signs you out on all devices.</p>
        <form className="form-grid" onSubmit={submit}>
          <label className="wide-field">
            Current password
            <input
              autoFocus
              name="current_password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={256}
            />
          </label>
          <label className="wide-field">
            New password
            <input
              name="new_password"
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={256}
            />
          </label>
          <label className="wide-field">
            Confirm new password
            <input
              name="confirm_password"
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={256}
            />
          </label>
          {error && (
            <p className="alert error-alert wide-field" role="alert">
              {error}
            </p>
          )}
          <div className="modal-actions">
            <button
              type="button"
              className="button outline"
              onClick={onClose}
              disabled={busy}
            >
              Cancel
            </button>
            <button className="button primary" disabled={busy}>
              {busy ? 'Saving…' : 'Change password'}
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}
