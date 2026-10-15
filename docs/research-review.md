# Research review

All URLs were checked on **2026-10-14**. Repository facts come from the GitHub REST API or the
repository front page on that date; paper metadata comes from Crossref and the publisher pages.
Capabilities listed are those **stated by the source**; they were not independently executed unless
noted. **No code from any reference was copied into this product.** Reuse notes describe what could
be reused after a licence and architecture review.

## Repositories

| # | Repository | Verified | Licence | Activity | Stated capabilities | Limitations for this product | Possible reuse |
|---|---|---|---|---|---|---|---|
| 1 | [harshit-vmr/Drone-Swarm-Simulator](https://github.com/harshit-vmr/Drone-Swarm-Simulator) | Resolves; "A unity project for Drone Swarm Simulation" | **None stated** (all rights reserved by default) | Last push 2023-06-25; 3 commits; 0 stars | Unity 2020.3.40f1 scenes; leader drone with waypoints | No licence, so no reuse permitted; small demo scope; no assessment or event model | Idea only: leader/follower formation display in a future Unity client |
| 2 | [mac799l/drone-swarm-simulation](https://github.com/mac799l/drone-swarm-simulation) | Resolves; "How to simulate a drone swarm using AirSim or Gazebo" | **None stated** | 95 commits, 5 stars; "in development" | Guide: Gazebo/ArduPilot SITL, AirSim (Colosseum, UE 5.4), MAVProxy, multi-drone setup, camera streams | Flight-control stack, not training assessment; no licence | None (reference reading on SITL setup) |
| 3 | [AngusMcGlynn/SwarmSAR](https://github.com/AngusMcGlynn/SwarmSAR) | Resolves; "drone swarm coordination simulator for autonomous search and rescue" | MIT (stated in README) | 3 commits, 0 stars | Python 3.11, pygame, 100+ agents, probabilistic sensor with occlusion, **seeded reproducibility**, metrics pipeline | Search-and-rescue domain; coordination algorithms not relevant to recognition training; very early project | Confirms the seeded headless-simulation pattern used in `drikr_simcore`; no code used |
| 4 | [iamaisim/ProjectAirSim](https://github.com/iamaisim/ProjectAirSim) | Resolves; "Microsoft's evolution of AirSim" | MIT | Active (push 2026-10-08), ~900 stars | High-fidelity UE-based aerial simulation, sensors, APIs | Heavy GPU/Unreal dependency; physics-level simulation far beyond training-picture needs; not offline-friendly to build | Candidate future high-fidelity visual back-end behind the same adapter protocol (requires evaluation) |
| 5 | [aau-cns/Ardupilot_Multiagent_Simulation](https://github.com/aau-cns/Ardupilot_Multiagent_Simulation) | Resolves; ArduPilot + ROS 2 + Gazebo multi-agent environment | **GPL-3.0** | 3 commits, 124 stars | Spawn multiple drones with namespaces and MAVLink IDs, sensor xacros, devcontainer | Copyleft licence incompatible with closed distribution; real flight-stack focus | None. Do not link or copy without legal review |
| 6 | [CodexLabsLLC/Colosseum](https://github.com/CodexLabsLLC/Colosseum) | Resolves; AirSim fork for Unreal with experimental Unity plugin | MIT | **Archived 2026-07-11** (read-only) | SITL/HIL with PX4/ArduPilot, Unreal plugin | Archived, so no maintenance or security fixes | Not recommended for new work |
| 7 | [monemati/multiuav-gazebo-simulation](https://github.com/monemati/multiuav-gazebo-simulation) | Resolves; multi-UAV Gazebo + ArduPilot tutorial | MIT | Last push 2023-05-17, 115 stars | Shell scripts and instructions for multiple quadcopters | Tutorial for flight simulation; no assessment features | None |
| 8 | [CNURobotics/flexible_drones](https://github.com/CNURobotics/flexible_drones) | Resolves; ROS 2 action-based heterogeneous drone coordination framework | Apache-2.0 | Push 2026-07-02, 0 stars | ROS 2 actions for multi-drone coordination | Coordination and control rather than human recognition training | None in this release |

**Conclusion.** None of the repositories provides a training-assessment workflow, versioned rubric
scoring, an AAR or role-based training records. Several provide flight-dynamics simulation, which
this product deliberately does not need: trainees interpret a synthetic *sensor picture*, so a
lightweight deterministic kinematic model is sufficient and keeps the system offline, testable and
reproducible. No novelty is claimed for seeded simulation, swarm formations or multi-agent
spawning, all of which appear in the references.

## Papers

| # | Reference (verified) | Relevance | How it informed this product | Limitations / caution |
|---|---|---|---|---|
| 1 | K. Tanaka, "A Survey on XR-Based Drone Simulation: Technologies, Applications, and Future Directions," *Drones and Autonomous Vehicles*, vol. 2, 10015, 2025. doi:10.70322/dav.2025.10015 | XR training simulators | Supports keeping VR optional: the adapter protocol allows a future XR client without making it mandatory | Survey; no specific validated training-transfer results used |
| 2 | A. Phadke, F. A. Medrano, C. N. Sekharan, T. Chu, "Designing UAV Swarm Experiments: A Simulator Selection and Experiment Design Process," *Sensors*, 23(17), 7359, 2023. doi:10.3390/s23177359 | Simulator selection | Informed ADR-001: choose fidelity to fit the experiment's purpose. Recognition training needs a reproducible sensor picture, not flight physics | Focus on research experiments rather than training products |
| 3 | A. Phadke, F. A. Medrano, C. N. Sekharan, T. Chu, "An analysis of trends in UAV swarm implementations in current research: simulation versus hardware," *Drone Systems and Applications*, vol. 12, pp. 1–10, 2024. doi:10.1139/dsa-2023-0099 | Simulation vs hardware | Supports software-only scope and explicit disclosure that synthetic behaviour is not validated against real systems | Trend analysis; not a training-effectiveness study |
| 4 | Z. Zhou, P. Wei, Z. Wang, L. Duan, S. Hai, Z. Zhang et al., "Towards human-centered interaction with UAV swarms: Framework, system design, and user study," *Design and Artificial Intelligence*, vol. 1, 100029, 2025. doi:10.1016/j.daai.2025.100029 | Human–swarm interaction | Swarm members shown as individual tracks that move together, with multi-select for group decisions | Different task (control, not recognition) |
| 5 | L. Xing, C. Cui, M. Wang, C. Xu, "From Detection to Countermeasure: A Review of Key Technologies in Counter-Unmanned Aerial Vehicle Systems," *IET Cyber-Systems and Robotics*, vol. 8, 2026. doi:10.1049/csy2.70048 | Detection sensor modalities | Only to choose **generic, abstract** simulated sensor categories (radar-like, optical, RF) with configurable quality. No operational parameters were taken from it | The countermeasure content is out of scope and was not used |
| 6 | Y. Alqudsi, M. Makaraci, "UAV swarms: research, challenges, and future directions," *Journal of Engineering and Applied Science*, vol. 72, 12, 2025. doi:10.1186/s44147-025-00582-3 | Swarm characteristics | Swarm formation types (line, wedge, cluster) as generic visual behaviours | Survey |
| 7 | M. Kaur, A. Kaur, P. Singh, "UAV swarm clustering and trajectory planning: A taxonomy, systematic review, current trends and research challenges," *Computers and Electrical Engineering*, vol. 128, 110697, 2025. doi:10.1016/j.compeleceng.2025.110697 (ScienceDirect page returned HTTP 403 to automated access; metadata verified via Crossref) | Swarm trajectories | Background only; the product uses simple scripted group behaviours | Full text not reviewed |
| 8 | E. Çetin, C. Barrado, J. L. Muñoz Gamarra, J. J. Ramos González, "Autonomous Cooperative Drone Swarms for Countering Drones via Multi-Agent Deep Reinforcement Learning," *Engineering Proceedings* (15th EASN Conference), 164, 2026. doi:10.3390/engproc2026133164 | Autonomous counter-drone RL | **Deliberately not used**: autonomous engagement optimisation is outside the safety boundary (brief §2, §6) | Recorded to show the scope decision |
| 9 | T. Yuan, D. Lovell, K. S. J. Pister, "Interceptor Swarms for Naval Defense: A Simulation-Based Evaluation of Hierarchical Swarm-vs.-Swarm Strategies," AIAA SCITECH 2026 Forum, p. 0750, 2026 (BSAC listing) | Unity-based Monte Carlo swarm simulator | Confirms Unity's use for batch swarm simulation (relevant to ADR-001). Interception strategy content not used | Full paper restricted |
| 10 | G. Karadeniz, A. Özcan, M. Bayram, G. İnce, "Drone Wars 3D: A Game-Based Simulation Platform for Testing Aerial Defence Strategies Against Drone Swarms," *Journal of Aeronautics and Space Technologies*, vol. 17 (Special Issue), 2024 | Game-based 3D swarm platform | Prior art for game-engine swarm visualisation; no novelty claimed for 3D swarm display | Author diacritics reconstructed from page metadata; site TLS certificate did not match its hostname at access time |

## Positioning

The contribution of this product is engineering integration, not new algorithms: a reproducible,
auditable training workflow (versioned scenarios, server-authoritative timing, transparent rubric
scoring, rules-based adaptive difficulty, AAR, exports) around a deliberately simple synthetic
sensor model. Training effectiveness has **not** been evaluated with users; that requires a study
design (brief §13), which is listed as an open item.
