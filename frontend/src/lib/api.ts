export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function parseError(r: Response): Promise<string> {
  const t = await r.text()
  try {
    const j = JSON.parse(t) as { detail?: unknown }
    if (typeof j.detail === 'string') return j.detail
    if (Array.isArray(j.detail)) return JSON.stringify(j.detail)
  } catch {
    /* ignore */
  }
  return t || r.statusText
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: 'include' })
  if (r.status === 401) throw new ApiError('Non connecté', 401)
  if (!r.ok) throw new ApiError(await parseError(r), r.status)
  return r.json() as Promise<T>
}

export async function apiPostJson<T>(
  path: string,
  body: Record<string, unknown>,
): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new ApiError(await parseError(r), r.status)
  return r.json() as Promise<T>
}

export async function apiPutJson<T>(
  path: string,
  body: Record<string, unknown>,
): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new ApiError(await parseError(r), r.status)
  return r.json() as Promise<T>
}

/** POST application/x-www-form-urlencoded (legacy FastAPI). Suit 303. */
export async function postFormNavigate(
  url: string,
  data: Record<string, string>,
): Promise<void> {
  const body = new URLSearchParams()
  Object.entries(data).forEach(([k, v]) => body.set(k, v))
  const r = await fetch(url, {
    method: 'POST',
    body,
    credentials: 'include',
    redirect: 'manual',
  })
  if (r.status === 303 || r.status === 302) {
    const loc = r.headers.get('Location')
    if (loc) window.location.assign(loc)
    return
  }
  if (r.ok) {
    window.location.reload()
    return
  }
  const msg = await r.text()
  throw new Error(msg.slice(0, 500) || `Erreur ${r.status}`)
}
