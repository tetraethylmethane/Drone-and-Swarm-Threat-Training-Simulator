# Research and open-source reuse

Re-verified on **2026-10-16**, building on the first review of 2026-10-14
([research-review.md](../research-review.md), which has the full notes). Repository facts come from
the GitHub REST API; paper metadata from the Crossref API (`api.crossref.org/works/<doi>`).

**Reuse decision: no code, models or assets from these sources are used in Drikr Systems.**
They informed architecture decisions only. `THIRD_PARTY_NOTICES.md` therefore lists no entries for
them.

## Repositories

| Repository | Licence (GitHub API) | Status on 2026-10-16 | Relevant capability | Decision |
|---|---|---|---|---|
| [harshit-vmr/Drone-Swarm-Simulator](https://github.com/harshit-vmr/Drone-Swarm-Simulator) | None detected | Last push 2023-06-25, 0 stars | Unity leader/follower swarm demo | Not reusable (no licence: all rights reserved). Idea only |
| [mac799l/drone-swarm-simulation](https://github.com/mac799l/drone-swarm-simulation) | None detected | Last push 2026-04-30 | Guide to Gazebo, ArduPilot SITL and AirSim swarms | Not reusable without a licence; reference reading |
| [AngusMcGlynn/SwarmSAR](https://github.com/AngusMcGlynn/SwarmSAR) | **None detected by GitHub** (the earlier review noted an MIT statement in the README) | Last push 2026-03-20 | Seeded, reproducible headless swarm simulation | Confirms the seeded-simulation pattern. **Licence needs clarification** (no LICENSE file) before any reuse |
| [iamaisim/ProjectAirSim](https://github.com/iamaisim/ProjectAirSim) | MIT | Active (push 2026-10-08), 905 stars | High-fidelity Unreal-based aerial simulation | Candidate future high-fidelity visual back-end behind the adapter protocol; heavy GPU dependency conflicts with the desktop-first position. Not adopted |
| [aau-cns/Ardupilot_Multiagent_Simulation](https://github.com/aau-cns/Ardupilot_Multiagent_Simulation) | GPL-3.0 | Push 2026-03-31, 124 stars | ArduPilot + ROS 2 + Gazebo multi-agent | Copyleft; flight-stack focus. Not used |
| [CodexLabsLLC/Colosseum](https://github.com/CodexLabsLLC/Colosseum) | NOASSERTION (licence file not recognised) | **Archived** | AirSim fork | Archived, no maintenance. Not recommended |
| [monemati/multiuav-gazebo-simulation](https://github.com/monemati/multiuav-gazebo-simulation) | MIT | Last push 2023-05-17 | Multi-UAV Gazebo tutorial | Flight simulation tutorial. Not needed |
| [CNURobotics/flexible_drones](https://github.com/CNURobotics/flexible_drones) | Apache-2.0 | Push 2026-07-02 | ROS 2 multi-drone coordination | Control, not training assessment. Not used |

None of the repositories offers training assessment, versioned rubrics, after-action review or
training records, which are Drikr's core.

## Papers (all six DOIs resolve)

| DOI | Title (Crossref) | Venue, year | Use in Drikr |
|---|---|---|---|
| [10.70322/dav.2025.10015](https://doi.org/10.70322/dav.2025.10015) | A Survey on XR-Based Drone Simulation: Technologies, Applications, and Future Directions | Drones and Autonomous Vehicles, 2025 | Supports keeping VR optional (P2), behind the same adapter protocol |
| [10.3390/s23177359](https://doi.org/10.3390/s23177359) | Designing UAV Swarm Experiments: A Simulator Selection and Experiment Design Process | Sensors, 2023 | Fidelity should match purpose: a reproducible sensor picture, not flight physics (ADR-001) |
| [10.1139/dsa-2023-0099](https://doi.org/10.1139/dsa-2023-0099) | An analysis of trends in UAV swarm implementations in current research: simulation versus hardware | Drone Systems and Applications, 2024 | Software-only scope; synthetic behaviour disclosed as not validated against real systems |
| [10.1016/j.daai.2025.100029](https://doi.org/10.1016/j.daai.2025.100029) | Towards human-centered interaction with UAV swarms: Framework, system design, and user study | Design and Artificial Intelligence, 2025 | Swarm members shown as individual tracks moving together; multi-select for group decisions |
| [10.1049/csy2.70048](https://doi.org/10.1049/csy2.70048) | From Detection to Countermeasure: A Review of Key Technologies in Counter-Unmanned Aerial Vehicle Systems | IET Cyber-Systems and Robotics | Only generic sensor categories (radar-like, optical, RF). **Countermeasure content deliberately not used** (safety boundary) |
| [10.1186/s44147-025-00582-3](https://doi.org/10.1186/s44147-025-00582-3) | UAV swarms: research, challenges, and future directions | Journal of Engineering and Applied Science, 2025 | Generic formation types (line, wedge, cluster) as visual behaviours |

## What the sources do not provide

None of them reports a validated **training-effectiveness** result for counter-drone recognition
training that Drikr could rely on. Drikr's evidence therefore comes from its own tests and its
synthetic assessment validation ([assessment-validation.md](assessment-validation.md)). A human
study is still required ([training-effectiveness-study-protocol.md](training-effectiveness-study-protocol.md)).

## Attribution

Not required: nothing was copied. If any of the permissively licensed projects (MIT, Apache-2.0)
are integrated later, add them to `THIRD_PARTY_NOTICES.md` with their licence text, and run the
licence and dependency review recorded in this file first.
