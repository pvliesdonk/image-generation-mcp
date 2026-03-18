# ADR-0004: Keyword-Based Provider Selection

## Status

Accepted

## Context

When `provider="auto"` (the default), the server must select the best provider
for the given prompt. Options range from simple keyword matching to LLM-based
classification.

## Decision Drivers

- **Zero latency** — selection should not require an API call
- **Predictable** — same prompt should always select the same provider
- **Transparent** — users should understand why a provider was selected
- **Extensible** — adding providers should be straightforward

## Considered Options

### Option 1: LLM-based classification

Use a small model to classify the prompt into categories and select a provider.

**Pros:** Handles nuance, context-aware.
**Cons:** Adds latency, requires a model, non-deterministic.

### Option 2: Keyword matching with fallback chain (chosen)

Regex word-boundary matching against a prioritized rule list. First matching
rule wins. If no rule matches, use a default fallback chain.

**Pros:** Zero latency, deterministic, easy to understand and extend.
**Cons:** Cannot handle subtle distinctions, new keywords must be manually added.

### Option 3: Embedding similarity

Embed prompt and compare to provider capability descriptions.

**Pros:** Handles semantic similarity.
**Cons:** Requires embeddings model, adds latency, overkill for 3 providers.

## Decision

**Option 2: Keyword matching with fallback chain.**

The selection rules are ordered lists of `(keywords, preferred_providers)`:

| Keywords | Preferred Provider Chain |
|----------|------------------------|
| realistic, photo, photography, headshot, portrait photo, product shot | a1111 → openai |
| text, logo, typography, poster, banner, signage, lettering, font | openai |
| quick, draft, test, placeholder, mock | placeholder |
| art, painting, illustration, watercolor, sketch | a1111 → openai |
| anime, manga, kawaii, chibi | a1111 → openai |

Default fallback (no keyword match): openai → a1111 → placeholder.

Keywords are matched using `\b` word boundaries to avoid false positives
(e.g., "art" should not match "start").

## Consequences

### Positive

- Instant selection — no API calls, no model inference
- Deterministic — same prompt always selects the same provider
- Easy to test — pure function with string input, string output
- Easy to extend — add a new tuple to `_SELECTION_RULES`

### Negative

- Cannot handle nuanced prompts ("a photorealistic painting" — is it photo or art?)
- Manual keyword maintenance as prompt patterns evolve
- First-match-wins means rule order matters

### Mitigation

Users can always specify `provider="openai"` or `provider="a1111"` explicitly
to override auto-selection. The MCP `select_provider` prompt guides the client
on when to use explicit selection.
