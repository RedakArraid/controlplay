import { ExternalLink, MapPin } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Card } from '../../components/Card'
import { apiGet } from '../../lib/api'

type PublicSalle = {
  id: number
  code: string
  name: string
  latitude: number | null
  longitude: number | null
}

function bboxForSalles(salles: PublicSalle[]): string | null {
  const pts = salles.filter(
    (s) => s.latitude != null && s.longitude != null,
  ) as (PublicSalle & { latitude: number; longitude: number })[]
  if (pts.length === 0) return null
  const lats = pts.map((p) => p.latitude)
  const lons = pts.map((p) => p.longitude)
  const pad = 0.02
  const south = Math.min(...lats) - pad
  const north = Math.max(...lats) + pad
  const west = Math.min(...lons) - pad
  const east = Math.max(...lons) + pad
  return `${west}%2C${south}%2C${east}%2C${north}`
}

export function CartePage() {
  const [salles, setSalles] = useState<PublicSalle[] | null>(null)

  useEffect(() => {
    apiGet<{ salles: PublicSalle[] }>('/public/salles')
      .then((d) => setSalles(d.salles))
      .catch(() => setSalles([]))
  }, [])

  const embedUrl = useMemo(() => {
    if (!salles?.length) return null
    const b = bboxForSalles(salles)
    if (!b) return null
    return `https://www.openstreetmap.org/export/embed.html?bbox=${b}&layer=mapnik`
  }, [salles])

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6 md:py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-cyan">Carte</p>
      <h1 className="font-display mt-2 text-4xl font-extrabold tracking-tight md:text-5xl">
        Nos <span className="text-gradient-brand">salles de jeu</span>
      </h1>
      <p className="mt-4 max-w-2xl text-lg text-cp-muted">
        Les marqueurs apparaissent lorsque les coordonnées GPS sont renseignées pour chaque salle dans
        l’administration. Sinon, la liste ci-dessous reste disponible avec liens vers chaque lieu.
      </p>

      {embedUrl ? (
        <Card className="mt-10 overflow-hidden p-0">
          <iframe
            title="Carte OpenStreetMap des salles"
            className="h-[420px] w-full border-0 grayscale-[0.2] contrast-[1.05]"
            src={embedUrl}
            loading="lazy"
          />
        </Card>
      ) : (
        <Card className="mt-10 flex flex-col items-center justify-center gap-3 border-dashed py-16 text-center">
          <MapPin className="h-10 w-10 text-cp-muted" />
          <p className="max-w-md text-sm text-cp-muted">
            Aucune coordonnée GPS en base pour l’instant. Ajoutez latitude / longitude sur vos fiches
            salle pour activer la carte embarquée.
          </p>
        </Card>
      )}

      <h2 className="font-display mt-14 text-xl font-bold">Liste des espaces</h2>
      <ul className="mt-6 grid gap-3 sm:grid-cols-2">
        {(salles ?? []).map((s) => (
          <li key={s.id}>
            <Card className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="font-mono text-xs text-cp-accent">{s.code}</p>
                <p className="font-medium">{s.name}</p>
                {s.latitude != null && s.longitude != null ? (
                  <p className="mt-1 text-xs text-cp-muted">
                    {s.latitude.toFixed(4)}, {s.longitude.toFixed(4)}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <a
                  href={`/salle/${encodeURIComponent(s.code)}`}
                  className="rounded-lg bg-white/10 px-3 py-2 text-xs font-medium hover:bg-white/15"
                >
                  Page salle
                </a>
                {s.latitude != null && s.longitude != null ? (
                  <a
                    href={`https://www.openstreetmap.org/?mlat=${s.latitude}&mlon=${s.longitude}#map=16/${s.latitude}/${s.longitude}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-cp-cyan/40 px-3 py-2 text-xs font-medium text-cp-cyan hover:bg-cp-cyan/10"
                  >
                    OSM
                    <ExternalLink className="h-3 w-3" />
                  </a>
                ) : null}
              </div>
            </Card>
          </li>
        ))}
        {salles && salles.length === 0 ? (
          <li className="text-sm text-cp-muted">Aucune salle.</li>
        ) : null}
        {!salles ? <li className="text-sm text-cp-muted">Chargement…</li> : null}
      </ul>
    </div>
  )
}
