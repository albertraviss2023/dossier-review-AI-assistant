# Model Policy (Gemma 4 Only)

## Effective Date
- 2026-04-05

## Policy
- The project uses only Google Gemma 4 models for all generation, retrieval augmentation logic, and ranking logic.
- No non-Gemma model family is allowed in runtime configuration, scripts, or deployment manifests.

## Approved Runtime Model
- `ai/gemma4:4B-Q4_K_XL`

## Implementation Rules
- Any inference client must default to Gemma 4.
- Any fallback route must still use Gemma 4 (different route profile is allowed, different model family is not).
- Any pull request adding alternative model families must be rejected unless this policy document is explicitly revised.
