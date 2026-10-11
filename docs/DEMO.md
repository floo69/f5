# SurakshitID — 3-minute judge demo

**One line:** Every day, millions of Indians hand photocopies of their Aadhaar to hotels, Xerox
shops and SIM counters. Those copies leak and fuel AePS fingerprint fraud and loan scams.
SurakshitID turns your ID into a copy that only works for one person, one purpose and a few
days, can't be edited without detection, and never leaves your device.

## Before you start
```sh
make api      # terminal 1
make portal   # terminal 2 (mock hotel website for Leak alerts)
make web      # terminal 3 → http://localhost:5173 (use Chrome's phone view, or your laptop)
```
Backup if anything breaks: http://localhost:5173/?mock=1 runs the whole UI on recorded data.

## The script

**1. Protect (60 s)** — *"I'm checking into a hotel in Goa."*
- Tap **Protect → Try a sample → Aadhaar front** (or take a live photo of a card).
- Choose **Hotel check-in**, type "Taj Hotel, Goa", 2 days — or type the voice command
  *"Hey Surakshit, armor my Aadhaar for Goa Taj Hotel for 2 days"*.
- Point out: photo is straightened and cleaned, GPS/camera metadata stripped, the first 8
  digits + QR are destroyed, last 4 kept (UIDAI masked-Aadhaar format), a diagonal purpose
  stamp crosses the photo and text: *"FOR TAJ HOTEL, GOA CHECK-IN ONLY · NOT VALID FOR
  BANKING, SIM, LOANS"*. Drag the before/after slider.
- Unclear photo? It still works: "careful mode" hides extra details instead of refusing.
  A truly blurry photo is refused ("We couldn't read this photo clearly") — fail-safe.

**2. Prove it (45 s)** — tap **How do we know it's safe?**
- Hidden areas are literally zero bytes (`00 00 00 …`), the PDF has no text to copy, no
  metadata. Brightening the image ×4 reveals nothing.
- Tap **Erase watermark** / **Swap photo** → red **This copy was edited** with the exact
  altered areas boxed. Every copy is sealed with a digital signature over a grid of tiny
  tiles, so any pixel change is located.

**3. Check & revoke (30 s)** — *"Now I'm the hotel clerk."*
- **Check a copy** → upload the downloaded PNG → green "Genuine copy · for Taj Hotel check-in".
- **My copies** → **Revoke** → check again → "The owner withdrew this copy". A leaked copy
  can be killed remotely.

**4. Leak alerts (30 s)** — *"What about copies already leaked?"*
- **Scan a demo hotel website** → agents browse the site, find 3 exposed IDs (shown already
  blacked out), open the UIDAI biometric-lock page and stop at the OTP ("your turn" — agents
  never type OTPs), then draft a DPDP Act 2023 takedown notice + cybercrime.gov.in / 1930.
- Say: *"Agents can only add protection. Deterministic rules decide what's safe — an AI
  can never mark something as safe."*

**5. Registry (optional, 15 s)** — the **Deeds** tab: the same engine redacts thumbprints and
Aadhaar numbers from land-registration deeds before government portals publish them (the
Haryana/Bihar/West Bengal silicone-thumb fraud).

## Why it wins
- **Real problem, real fraud:** AePS fingerprint cloning from public deeds; Aadhaar photocopies
  everywhere. DPDP Act 2023 makes data minimisation a legal duty.
- **Destroy, don't hide:** pixels overwritten, flattened, verified after export — not a
  black box over selectable text.
- **Purpose binding + revocation:** what UIDAI's masked Aadhaar lacks.
- **Zero trust:** runs on the device; the decision gate is pure rules (decides in ~0.01 ms).
- **Tech:** OpenCV + Tesseract on-device detection (Verhoeff-checked Aadhaar, PAN, QR, faces,
  thumbprints), Ed25519 signature + tile hashes + hash-chained ledger, MCP servers (scanner,
  redactor, verifier), an allowlisted browser agent (Playwright MCP), multi-agent
  orchestrator with Claude wiring (live/replay/off modes and a cost cap).

## Honest limits (say them before a judge asks)
- Only lossless copies verify; a re-photographed copy shows as edited (by design: never a
  false "genuine").
- Detection is tuned on synthetic cards; very small screenshots (< ~800 px) get careful mode.
- The Claude-powered agent mode needs Claude enabled on the AWS/Anthropic account; the demo
  runs the same agents on built-in rules at $0.
