# Verity Canonicalization Specification

## 1. Introduction

The Verity Canonicalization Specification defines a set of deterministic rules for sources, claims, and assertions before applications construct a graph. It specifies how data is normalized before being serialized into a canonical representation. This enables applications to exchange canonicalized data without any ambiguity.

## 2. Design Goals

The Verity Canonicalization Specification is designed to produce consistent graph structures across independent implementations. To achieve this, it follows these design goals:

- **Deterministic** — Semantically equivalent input should always produce an identical representation.
- **Domain-Agnostic** - The specification operates the same regardless of an application's underlying data.
- **Language-Independent** — Compliant implementations produce identical results regardless of the programming language used.
- **Versioned** - The specification can evolve without breaking existing implementations.
  
## 3. Source Canonicalization

### 3.1 Source Identifiers

A source refers to the origin asserting one or more claims.

An application MUST define the source type before invoking the Verity SDK. The SDK MUST NOT infer the source type based on the source identifier provided.

Supported source types include:

- `web_publisher`
- `web_document`
- `internal_resource`
- `internal_service`
- `database`
- `package`

### 3.2 Normalization Rules

For `web_publisher` sources, the SDK MUST:

- Make the domain name lowercase.
- Strip a trailing DNS dot from the domain name.
- Transform internationalized domain names using Unicode Technical Standard #46 (UTS #46) Nontransitional Processing      before converting them to their IDNA2008 ASCII representation.
- Permit an empty path or the root path (/).
- Reject identifiers containing any other path, query, or fragment information.

For `web_document` sources, the SDK MUST:

- Make the URI scheme and host lowercase.
- Strip default ports.
- Strip URI fragments.
- Keep paths and query parameters intact.
- Normalize the URI according to RFC 3986.

For all source types, the SDK MUST reject identifiers that cannot be deterministically normalized.

### 3.3 Examples

Input

```text
https://docs.anthropic.com/
```

Canonical

```text
docs.anthropic.com
```

---

Input

```text
HTTPS://Example.com:443/docs/api#section
```

Canonical

```text
https://example.com/docs/api
```

---

Input

```text
Confluence:Page:184920
```

Canonical

```text
confluence:page:184920
```

---

Input

```text
internal-wiki
```

Result

```text
Rejected
```

Reason

```text
The identifier cannot be deterministically normalized.
```

## 4. Claim Canonicalization

### 4.1 Entity

An entity represents the subject of one or more claims.

The SDK MUST:

- Accept structured entity identifiers only.
- Preserve the semantic identity provided by the client.
- Normalize Unicode strings using Unicode Normalization Form C (NFC).
- Trim surrounding whitespace.
- Lowercase the entity only when explicitly specified by the identifier namespace.
- Reject entity identifiers that cannot be deterministically normalized into a unique canonical representation.

Examples:

Input

```text
Python
```

Canonical

```text
python
```

---

Input

```text
 payment_service
```

Canonical

```text
payment_service
```

### 4.2 Attribute

An attribute represents the property of an entity.

The SDK MUST:

- Lowercase the attribute.
- Trim surrounding whitespace.
- Collapse repeated whitespace.
- Replace spaces with underscores.
- Preserve numeric characters.
- Preserve existing snake_case identifiers.
- Reject empty attributes.

Examples:

Input

```text
Supports Streaming
```

Canonical

```text
supports_streaming
```

---

Input

```text
Retry Policy
```

Canonical

```text
retry_policy
```

---

Input

```text
Latency MS
```

Canonical

```text
latency_ms
```

### 4.3 Value

Values are canonicalized based on the underlying data type.

The SDK MUST:

- Normalize boolean values.
- Normalize numeric representations.
- Trim surrounding whitespace for string values.
- Preserve the semantic meaning of the string value.

Examples:

Input

```text
TRUE
```

Canonical

```text
true
```

---

Input

```text
0042
```

Canonical

```text
42
```

---

Input

```text
4.500
```

Canonical

```text
4.5
```
  
### 4.4 Units

Unit normalization is outside the scope of this specification.

Clients are responsible for converting measurements into deterministic units before invoking the Verity SDK.

## 5. Assertion Construction

### 5.1 Source

Each assertion MUST reference exactly one canonical source.

The source MUST satisfy the requirements specified in Section 3.

### 5.2 Claim

Each assertion MUST reference exactly one canonical claim.

The claim MUST satisfy the requirements specified in Section 4.

### 5.3 Assertion

An assertion refers to the relationship between one canonical source and one canonical claim.

The SDK MUST:

- Construct assertions using only canonical sources and canonical claims.
- Preserve the direction of the relationship from source to claim.
- Reject assertions that include non-canonical sources or claims.
- Reject duplicate assertions within the submitted graph.

Examples:

```text
Source:
docs.anthropic.com

Claim:
(messages_api, supports_streaming, true)

Assertion:
docs.anthropic.com -> (messages_api, supports_streaming, true)
```

---

```text
Submitted Graph Update

docs.anthropic.com -> (messages_api, supports_streaming, true)

docs.anthropic.com -> (messages_api, supports_streaming, true)

Result:
Rejected

Reason:
Duplicate assertion within the submitted graph.
```

---

```text
Source:
HTTPS://Docs.Anthropic.com/

Claim:
(Messages API, Supports Streaming, TRUE)

Result:
Rejected

Reason:
Assertions MUST reference canonical sources and canonical claims.
```

## 6. Canonical Forms

Prior to generating linkage tokens, canonical sources, claims, and assertions MUST be serialized into deterministic JSON using the JSON Canonicalization Scheme as described in RFC 8785.

The serialized representation MUST be consistent across compliant implementations.

### 6.1 Canonical Source

Canonical source format MUST include:

- Source type
- Canonical identifier

Example

```json
{
  "kind": "web_publisher",
  "identifier": "docs.anthropic.com"
}
```

### 6.2 Canonical Claim

Canonical claim format MUST include:

- Entity
- Attribute
- Value

Example

```json
{
  "entity": "messages_api",
  "attribute": "supports_streaming",
  "value": true
}
```

### 6.3 Canonical Assertion

Canonical assertion format MUST include:

- Canonical source
- Canonical claim

Example

```json
{
  "source": {
    "kind": "web_publisher",
    "identifier": "docs.anthropic.com"
  },
  "claim": {
    "entity": "messages_api",
    "attribute": "supports_streaming",
    "value": true
  }
}
```

## 7. Versioning

The Verity Canonicalization Specification is versioned. Any modifications that affect canonicalization behavior MUST be introduced through a new specification version.

Implementations SHOULD expose the version of the specification they implement.

## 8. Conformance

The normative keywords MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT, RECOMMENDED, MAY, and OPTIONAL in this specification are to be interpreted as defined in RFC 2119 and RFC 8174.

An implementation is in compliance with this specification if it satisfies all normative requirements defined in this document.

Implementations MAY provide additional functionality, provided it does not alter the canonical representation produced by this specification.
