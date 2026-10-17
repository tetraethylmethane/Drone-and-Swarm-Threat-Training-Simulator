# Competitor landscape

**Accessed:** 2026-10-16 (all sources). **Method:** each company's own public website was read.
Where the site was unavailable, published press coverage was used and marked as secondary. Product
claims below are the vendors' own words unless marked otherwise. Nothing was tested hands-on, and
no customer, price or performance figure was added beyond what a source states. The individual
claims, quotes and open questions are in [competitive-evidence.md](competitive-evidence.md).

**Reading the matrix.** `Documented`: the source states the capability explicitly.
`Partially documented`: the source mentions it without describing how it works.
`Unknown`: the public material does not establish it either way. This is **not** evidence that the
capability is missing. `Not applicable`: the offering is not a training product of this kind.

## Who the companies are

| Company | What it offers (per its site) | Maturity and size (as publicly evident) | Relevance to Drikr | Confidence |
|---|---|---|---|---|
| DefenceVR (Aonix), India | VR simulator family including **KAVACH-SIM**, a "counter-drone warfare simulator" (detect, classify, track; 30+ threat models; swarms of 10 to 100+), UDAAN-SIM drone pilot trainer, field kit with Meta Quest 3 | Emerging; self-described Aonix product, Giridih, Jharkhand. On-site demos offered; procurement routes listed (iDEX, ADITI, DRDO TDF, MAKE-II). No named contracts | **High**: closest stated scope (counter-drone recognition training with AAR analytics) | Medium (vendor site only) |
| VR Astra by Aveera (Aveera Infotech Pvt Ltd), India | Immersive VR training systems: Drone / UAV Simulator (flight, ISR), tank and driving simulators, K-12 VR. "Real-time performance analytics, adaptive scoring, and post-training reports" | Emerging to growing; multi-sector VR company. Price "starts from ₹2.5L"; demos in 48 h | Medium: drone *operator* training, not counter-drone; analytics claimed | Medium |
| Zen Technologies, India | Established training-simulation company (live, virtual, constructive; Combat Training Centre) plus an operational **Anti Drone System** (RF, EO, X-band radar, jammer, hard kill) and **Zen UAV Sim** for UAV crews | Established defence contractor; "1000+ solutions deployed"; publishes investor information and annual reports | Medium: broad training portfolio. No counter-drone *training* product found on the pages read | Medium |
| Big Bang Boom Solutions, India | Operational counter-drone systems (Vajra detection, jamming and radar), other defence products; a Portable Shooting Range (live fire); "AI Fighter Pilot Training" listed without detail | Growing defence start-up (self-described iDEX start-up); claims contracts and exports (self-reported) | Low: operational C-UAS hardware, not simulation training | Medium |
| Unistring Tech Solutions, India | Electronic warfare, counter-UAS, radar, and **radar simulators** (radar target and signal simulators). One drone-mounted target simulator is stated as usable "for training radar operators" | Established specialist EW company (DRDO collaboration stated) | Low: RF/radar test equipment rather than operator-decision training | Medium |
| MAK Technologies, international | **FPV Drone Simulator**: real FPV headsets and controllers, MAK ONE synthetic environment on global terrain, optional AI drone-swarm coordinator, counter-drone play through VR-Engage | Established simulation software vendor | Medium: high-fidelity flight and swarm simulation and counter-drone play; different emphasis (pilot skills and entity simulation) | Medium |
| Red 6, international | **ATARS**: airborne augmented reality for fighter-pilot training with synthetic threats | Growing, well-funded aviation-training company | Low: aviation AR. No drone or counter-drone content found | High (scope) |
| Bagira Systems, international | Live, virtual, constructive simulation line including a **UAV Mission Simulator**, JTAC, artillery and force-on-force | Established simulation company (a holding company with general meetings is linked) | Low to medium: UAV mission training listed; counter-drone not stated | Low (sparse product detail) |
| Combatica, international | Tactical VR *entertainment* experience "built on Special Forces Training Tech"; "Launching Soon" | Emerging; consumer-facing launch announced | Low: no drone content found; consumer product | Medium |
| Althimis (sources say "Althimis Inc."), international | **Guardian**, a counter-drone readiness and mission-simulation platform, with an "AI Chaos Engine (A²CE)" that generates attack scenarios. Field demonstration with Bundeswehr operators reported July 2026 | Emerging (secondary sources: founded 2023, seed funding). **Company website returned HTTP 403**; identity as "Althimis Defense" not confirmed | **High**: counter-drone readiness assessment with outcome categories | Low (secondary sources only) |

## Capability matrix (public documentation only)

Columns: DVR = DefenceVR, VRA = VR Astra, ZEN = Zen Technologies, BBB = Big Bang Boom, UNI =
Unistring, MAK = MAK Technologies, R6 = Red 6, BAG = Bagira, CMB = Combatica, ALT = Althimis.

Updated 2026-10-16 (Sprint 10) from the verification table in competitive-evidence.md: DVR adaptive
training (vendor claim, mechanism unknown) and ZEN counter-drone training content (drone threats
in an air-defence gunnery simulator) moved from Unknown to Partially documented. Every other
Unknown stays Unknown.

| Dimension | DVR | VRA | ZEN | BBB | UNI | MAK | R6 | BAG | CMB | ALT |
|---|---|---|---|---|---|---|---|---|---|---|
| Counter-drone *training* content | Documented | Unknown | Partially documented | Not applicable | Partially documented | Partially documented | Unknown | Unknown | Unknown | Documented |
| Standard desktop deployment | Partially documented | Unknown | Unknown | Not applicable | Not applicable | Unknown | Not applicable | Unknown | Unknown | Unknown |
| Offline operation | Documented | Unknown | Unknown | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Unknown |
| Scenario creation and controlled randomisation | Partially documented | Unknown | Partially documented | Not applicable | Not applicable | Partially documented | Unknown | Unknown | Unknown | Partially documented |
| Reproducibility of sessions | Unknown | Unknown | Unknown | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Unknown |
| Transparency of scoring and assessment | Partially documented | Partially documented | Partially documented | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Partially documented |
| Individual and unit-level reporting | Partially documented | Partially documented | Partially documented | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Unknown |
| Progress tracking across sessions | Unknown | Partially documented | Unknown | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Unknown |
| Adaptive training on demonstrated competency | Partially documented | Partially documented | Unknown | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Unknown |
| Instructor usability | Unknown | Unknown | Unknown | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Unknown |
| Accessibility and interface clarity | Unknown | Unknown | Unknown | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Unknown |
| Automated testing and reliability | Unknown | Unknown | Unknown | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Unknown |
| Data integrity, access control, audit | Unknown | Unknown | Unknown | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Unknown |
| Integration effort and hardware stated | Documented | Partially documented | Partially documented | Not applicable | Not applicable | Partially documented | Unknown | Unknown | Unknown | Unknown |
| Published evidence of training effectiveness | Unknown | Unknown | Unknown | Not applicable | Not applicable | Unknown | Unknown | Unknown | Unknown | Unknown |

What the matrix does **not** show: that any competitor lacks a capability marked `Unknown`. Most
defence training products are documented in brochures, on request and in procurement documents
that are not public. Several `Unknown` cells are likely to be capabilities that exist but were not
described on the pages read.

## Drikr Systems on the same dimensions (own evidence, not a comparison)

| Dimension | Drikr status | Evidence |
|---|---|---|
| Counter-drone training content | Implemented: recognition and decision training on a synthetic sensor picture; no engagement content (by design) | Demo scenarios; `docs/architecture/scoring-model.md` |
| Standard desktop deployment | Implemented: browser client; Unity desktop client for Windows, Linux and macOS. No VR or special hardware | `docs/SPRINT_STATUS.md`; Linux smoke test in Docker |
| Offline operation | Tested on one machine; must be repeated on target hardware | `docs/operations/offline-deployment.md` verification record |
| Scenario creation and controlled randomisation | Implemented and tested: scenario editor, procedural generation, seeds, versioning | `test_procedural_*`, E2E instructor spec |
| Reproducibility | Implemented and tested: deterministic timelines, digests, per-session and bulk verification | `tests/reproducibility` (40 tests), `/admin/reproducibility` |
| Transparency of scoring | Implemented and tested: versioned rubric decision tree, per-item credits and reasons, evidence events | `test_traceability.py`, scoring model |
| Individual and unit-level reporting | Implemented and tested (units added 2026-10-16) | `test_units.py` |
| Progress tracking | Implemented and tested: progress, competency trends, recurring errors, attempt comparison | `test_competency.py` |
| Adaptive training | Implemented: rules-based with recorded reasons. Synthetic validation found it lags improving learners | `docs/research/assessment-validation.md` E5 |
| Instructor usability | **Not evaluated with users** | Usability study proposed (`docs/product/requirements-to-tests.md`) |
| Accessibility | Automated axe checks pass on key web pages; Unity screen-reader path verified via UI Automation; **no user sessions** | E2E accessibility spec; `scripts/unity-a11y-check.ps1` |
| Automated testing | Python, web, E2E, Unity and reproducibility suites; CI on GitHub | `docs/SPRINT_STATUS.md` |
| Data integrity, access control, audit | Implemented and tested: RBAC, MFA, hash-chained audit (tamper-evident, not tamper-proof), retention | Security docs |
| Integration effort and hardware | Docker Compose on one host; measured figures in `docs/product/positioning.md` | Measured on the development machine only |
| Evidence of training effectiveness | **None with people.** Synthetic validation of the measurement only; study protocol written | `docs/research/` |

## Where Drikr could credibly differ (hypotheses)

From the documented material, the most crowded areas are immersion (VR, AR, motion platforms, real
controllers), operational counter-drone hardware, and broad simulator portfolios. Established
companies have the advantage there, and Drikr should not try to compete on them.

The public material says the least about **how assessments are made and checked**:
- reproducibility of a session;
- transparency of scoring rules;
- traceability from a score to recorded events;
- auditability of training records;
- evidence that the training works.

These are the areas Drikr has built and tested. They are where a credible position is possible,
**provided** user evaluation confirms that instructors value them. Some competitors may also
offer them without publishing it. See [positioning.md](../product/positioning.md).
