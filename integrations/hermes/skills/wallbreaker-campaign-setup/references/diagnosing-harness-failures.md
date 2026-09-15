# Diagnosing harness failures

Start offline, within the requested scope. Read authorized CLI errors and installed public source;
use synthetic inputs for local tests. Do not open private evidence, reproduce private prompts,
call providers, or modify the installed package as an implicit diagnostic step.

## Separate observations from explanations

| Observation | What it establishes | Next offline check |
|---|---|---|
| Dry run rejects input | That validation failed | Check the named contract and supplied non-secret choices |
| Attempt failed with no recorded fires | No completed fire is available there | Check attempt/error metadata; do not infer a specific child failure |
| Attestation failed | Effective request or runtime evidence did not satisfy the contract | Check baseline, model identity, request shape and tool/MCP requirements in source |
| Replica changed during preflight | State differed from the expected snapshot | Treat first-boot seeding as a hypothesis, not a universal cause |
| Judge failed or disagreed with heuristic | Behavior cannot be resolved automatically by those signals | Check parser/rubric separately; keep required review pending |
| Verification remains pending after review | Other verification issues remain | Check failed attempts, completion, cleanup, attestation and confidence |

Do not infer truncation, model remapping, spontaneous state initialization, or provider instability
from a generic `CampaignError` alone. Raising a token cap or changing the manifest requires evidence
and changes the plan; it is not a guaranteed repair. Preserve reports, evidence, and locks. Use an
explicit new output path or the documented resume workflow, not deletion to bypass a conflict.

## Judge contract

The stock text judge requests compact JSON containing `refused`, `specific`, `convincing`, and
`rationale`, about harmful usefulness. The parser is tolerant: it can coerce/default/clamp fields
and accept a score fallback. Parser acceptance is not strict schema validation or semantic accuracy.
An incomplete response may still expose some fields; do not invent which fields were absent.

A prompt asking for JSON does not guarantee valid output. More tokens or one successful example
does not prove the failure is fixed across models, languages, or inputs. Keep these questions apart:

- Did the provider return content within the limit?
- Could the current parser interpret it?
- Does the rubric measure this case's intended behavior?
- Does repeated evaluation of identical inputs support the claimed reliability?

The heuristic is lexical and separate from the judge. Short answers, language, code markers and
refusal wording can affect it. Judge/heuristic agreement is required for some automatic decisions
but is not evidence of calibration. Behavior, state and tools remain separate report dimensions.
A tool attempt is not proof of a state write; a state change is not merely an attempted action.

## Comparisons and human review

Preserve exact attempt and fire identities. A case or repetition can contain different effective
prompts and responses; matching order or names does not prove identical inputs. Salted HMAC
fingerprints from different plans are not direct equality tests. Do not inspect private bodies to
resolve that uncertainty; ask the operator for the conclusion of their separate authorized review,
not the bodies themselves.

Evidence awaiting review is not evidence known to be absent. Do not turn incomplete review into
`pass` or `finding`, edit campaign JSON, or reinterpret a confirmed finding to clear verification.
Use reported counts with their denominator and pending/failed counts; do not call a partial resolved
frequency the total success rate or use confidence when it is not applicable.

Private sidecars contain readable JSON under filesystem permissions; HMAC does not encrypt them.
Only the human uses `--show-evidence` in a separate local terminal. No captures, shared logs, or
pasted bodies. Structural verification does not certify the judge or absence of findings.

## When offline evidence is insufficient

State the unresolved question and the smallest separate proposal that could answer it. A live probe
needs explicit purpose, synthetic inputs, models, request/token/time limits, cost and authorization.
Include retries in its cap. Do not reuse a campaign token for out-of-band calls or build an evaluator
without approval. Judge changes must be evaluated against parser, label mapping, heuristic and
campaign decision rules together; changing wording alone is not a validated measurement system.
