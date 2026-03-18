# ADR-0002: Provider Protocol and Registry Pattern

## Status

Accepted

## Context

The server needs to support multiple image generation backends with different
APIs. Providers must be:

1. Independently implementable and testable
2. Conditionally registered based on available credentials
3. Discoverable by the MCP client (via `list_providers`)
4. Selectable by name or automatically by prompt analysis

## Decision Drivers

- **Type safety** — Provider implementations should be statically verifiable
- **Runtime flexibility** — Providers are registered at startup, not import time
- **No inheritance tax** — Providers should not need to extend a base class

## Considered Options

### Option 1: ABC base class

```python
class BaseImageProvider(ABC):
    @abstractmethod
    async def generate(self, ...) -> ImageResult: ...
```

**Pros:** Familiar, IDE support.
**Cons:** Forces inheritance, harder to test with simple mocks.

### Option 2: Runtime-checkable Protocol (chosen)

```python
@runtime_checkable
class ImageProvider(Protocol):
    async def generate(self, ...) -> ImageResult: ...
```

**Pros:** Structural typing, any object with the right shape works, easy to mock.
**Cons:** Slightly less discoverable than ABC.

### Option 3: Callable / function-based

Each provider is just an async function with the right signature.

**Pros:** Maximum simplicity.
**Cons:** No place for provider state (API keys, HTTP clients, presets).

## Decision

**Option 2: Runtime-checkable Protocol** with a **registry pattern** in
`ImageService`.

Providers are classes that implement the `ImageProvider` protocol. They are
registered by name in `ImageService` during server lifespan:

```python
service.register_provider("openai", OpenAIImageProvider(api_key=key))
service.register_provider("a1111", A1111ImageProvider(host=url))
service.register_provider("placeholder", PlaceholderImageProvider())
```

Registration happens in `_server_deps.py` lifespan, gated on config:
- Placeholder: always registered
- OpenAI: registered when `openai_api_key` is set
- A1111: registered when `a1111_host` is set

## Consequences

### Positive

- Providers are structurally typed — any object with `async generate(...)` works
- Registry allows conditional registration without provider code knowing about config
- `isinstance(obj, ImageProvider)` works at runtime for validation
- Simple to add new providers: implement the protocol, add registration logic

### Negative

- Protocol doesn't enforce implementation at import time (only at registration/use)
- Registry is mutable — must be careful about thread safety if providers are
  added/removed after startup (not currently needed)

### Provider Registration Location

Provider registration lives in `_server_deps.py` (lifespan), not in `service.py`.
This keeps the service layer config-agnostic: it accepts providers, doesn't know
where they come from. The lifespan function is the composition root.
