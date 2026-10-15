# Instructor guide

## Scenarios

* **Scenarios** lists the latest version of each scenario. *Demonstration* marks shipped demo content.
* **New scenario** opens the editor: basics, learning objectives, environment (with presets),
  simulated sensor quality, virtual entity groups (ranges are randomisation constraints), scripted
  events, and randomisation/difficulty/time/rubric settings. A JSON tab allows direct editing.
* **Validate on server** checks structure and cross-field rules and runs the scenario once with its
  seed and difficulty. Errors list the field path. A scenario cannot be saved until valid.
* **Generate scenario** builds a valid draft from a seed and constraints for you to review; the same
  inputs always produce the same draft.
* **Edit as new version** never changes the existing version or sessions run on it.
* **Planning preview** expands a version with any seed and level and shows the resulting entities.
  It contains ground truth and is visible to instructors only.
* **Archive** removes a scenario from new assignments; existing records are kept.

## Scoring rubrics

Rubrics define dimension weights (must sum to 1.0), timing thresholds, uncertainty credits, partial
credit, the decision tree for expected responses, and procedural rules. Editing creates a new
version; scores always record the version used. See `docs/architecture/scoring-model.md`.

## Assignments

**New assignment**: choose the scenario version, one or more trainees, title and instructions,
maximum attempts, due date, feedback level (*detailed* shows track ground truth and allows PDF export
to the trainee; *summary* does not), difficulty (*fixed*, or *adaptive* within your minimum and
maximum), and which options the trainee may choose (time of day, weather, custom seed).

## Reviewing sessions

**Sessions and reviews** filters by trainee, scenario, status and review state, and exports CSV for
the current filters. Open a session to see the AAR:

* **Summary**: overview, overall result, performance breakdown with weights and contributions,
  objectives, feedback.
* **Track decisions**: ground truth, classification, timing, response, rubric expectation and credit.
* **Event timeline**: the stored log by category (decisions, exercise, observations, ground truth)
  and track, paginated.
* **Error analysis**: incorrect classifications, missed tracks, inconsistent decisions,
  overconfidence, procedural violations and practice areas.
* **Instructor review**: status, strengths, improvements, focus objectives, private notes, and
  whether to share with the trainee (notes are never shared).
* **Export and verification**: PDF report; *Verify reproducibility* regenerates the timeline from the
  stored configuration and seed and re-scores the stored events.

## Analytics

Filter by trainee, scenario, objective and date range. Charts show overall score over time,
dimension averages and difficulty, computed only from persisted, scored sessions.
