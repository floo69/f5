import { useCallback, useEffect, useRef, useState } from 'react'
import { ICONS } from '../helpers'
import { Icon } from '../ui'
import { btnSecondary } from './styles'

type TorchTrack = Omit<MediaStreamTrack, 'getCapabilities'> & {
  getCapabilities?: () => MediaTrackCapabilities & { torch?: boolean }
}

interface Props {
  onCapture: (blob: Blob) => void
  onCancel: () => void
}

/** Camera with an ID-card alignment guide (85.6:54). Stops all tracks on unmount. */
export default function CameraCapture({ onCapture, onCancel }: Props) {
  const video = useRef<HTMLVideoElement>(null)
  const stream = useRef<MediaStream | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const [torchOk, setTorchOk] = useState(false)
  const [torch, setTorch] = useState(false)

  useEffect(() => {
    let dead = false
    void (async () => {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        setError(
          'The camera is unavailable here. Browsers only allow camera access on https or localhost. Open this app over https (or on localhost), or upload a photo instead.',
        )
        return
      }
      try {
        const s = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: 1920 } },
          audio: false,
        })
        if (dead) {
          s.getTracks().forEach((t) => t.stop())
          return
        }
        stream.current = s
        const track = s.getVideoTracks()[0] as unknown as TorchTrack | undefined
        setTorchOk(Boolean(track?.getCapabilities?.().torch))
        if (video.current) {
          video.current.srcObject = s
          await video.current.play().catch(() => undefined)
        }
        setReady(true)
      } catch (e) {
        const name = e instanceof DOMException ? e.name : ''
        setError(
          name === 'NotAllowedError'
            ? 'Camera permission was denied. Allow camera access in your browser settings, or upload a photo instead.'
            : name === 'NotFoundError'
              ? 'No camera was found on this device. Upload a photo instead.'
              : 'Could not start the camera. Upload a photo instead.',
        )
      }
    })()
    return () => {
      dead = true
      stream.current?.getTracks().forEach((t) => t.stop())
      stream.current = null
    }
  }, [])

  const toggleTorch = async () => {
    const track = stream.current?.getVideoTracks()[0]
    if (!track) return
    try {
      await track.applyConstraints({ advanced: [{ torch: !torch } as MediaTrackConstraintSet] })
      setTorch(!torch)
    } catch {
      setTorchOk(false)
    }
  }

  const shoot = useCallback(() => {
    const v = video.current
    if (!v || !v.videoWidth) return
    const c = document.createElement('canvas')
    c.width = v.videoWidth
    c.height = v.videoHeight
    c.getContext('2d')?.drawImage(v, 0, 0)
    c.toBlob((b) => { if (b) onCapture(b) }, 'image/jpeg', 0.92)
  }, [onCapture])

  if (error) {
    return (
      <div role="alert" className="space-y-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-900 ring-1 ring-amber-200">
        <p>{error}</p>
        <button type="button" onClick={onCancel} className={btnSecondary}>Back</button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="relative w-full overflow-hidden rounded-xl bg-black" style={{ aspectRatio: '3 / 4' }}>
        <video ref={video} playsInline muted className="absolute inset-0 h-full w-full object-cover" aria-label="Camera preview" />
        {/* Card-shaped guide: the huge box-shadow dims everything outside it. */}
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-4">
          <div className="relative w-full" style={{ aspectRatio: '85.6 / 54', boxShadow: '0 0 0 100vmax rgb(0 0 0 / 0.55)' }}>
            {(['left-0 top-0 border-l-4 border-t-4 rounded-tl-lg', 'right-0 top-0 border-r-4 border-t-4 rounded-tr-lg',
              'left-0 bottom-0 border-l-4 border-b-4 rounded-bl-lg', 'right-0 bottom-0 border-r-4 border-b-4 rounded-br-lg'] as const).map((c) => (
              <span key={c} className={`absolute h-8 w-8 border-white ${c}`} />
            ))}
          </div>
        </div>
        <p className="pointer-events-none absolute inset-x-0 bottom-3 px-4 text-center text-xs font-medium text-white drop-shadow">
          Fit the card inside the frame · avoid glare
        </p>
        {!ready && <p className="absolute inset-0 flex items-center justify-center text-sm text-white/80" role="status">Starting camera…</p>}
      </div>
      <div className="flex items-center justify-between gap-3">
        <button type="button" onClick={onCancel} className={btnSecondary}>Cancel</button>
        <button type="button" onClick={shoot} disabled={!ready} aria-label="Take photo"
          className="flex h-16 w-16 items-center justify-center rounded-full border-4 border-accent-700 bg-white shadow-md disabled:opacity-50">
          <span className="h-11 w-11 rounded-full bg-accent-700" />
        </button>
        {torchOk ? (
          <button type="button" onClick={() => void toggleTorch()} aria-pressed={torch} className={btnSecondary}>
            <Icon d={ICONS.bolt} className="h-5 w-5" />{torch ? 'Torch on' : 'Torch'}
          </button>
        ) : (
          <span className="w-[88px]" />
        )}
      </div>
    </div>
  )
}
