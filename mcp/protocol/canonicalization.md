# Verity Canonicalization Specification

## 1. Introduction

- Purpose of deterministic canonicalization

## 2. Design Goals

- Deterministic

- Domain agnostic

- Versioned

- Language independent

## 3. Canonicalization Workflow

- Structured assertions
- Deterministic normalization
- Canonical graph representation
  
## 4. Source Canonicalization

- Source identifiers

- Normalization rules

### 4.1 Source Identifiers

A source refers to the origin of one or more claims.

Clients MUST define the source type prior to invoking the Verity SDK. The SDK MUST NOT infer the source identity based on the source identifier provided.

Types of sources that are supported include:

- `web_publisher`
- `web_document`
- `internal_resource`
- `internal_service`
- `database`
- `package`

### 4.2 Normalization Rules

For `web_publisher` sources, the SDK MUST:

- Make the domain name lowercase.
- Strip a trailing DNS dot from the domain name.
- Transform internationalized domain names through IDNA.
- Fail for identifiers containing path, query, or fragment information.

For `web_document` sources, the SDK MUST:

- Make the URI scheme and host lowercase.
- Strip default ports.
- Strip URI fragments.
- Keep paths and query parameters intact.
- Normalize the URI according to RFC 3986.

For all source types, the SDK MUST reject ambiguous identifiers that cannot be deterministically normalized.

### 4.3 Examples

Examples:

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
Source identifier is ambiguous.
```

## 5. Claim Canonicalization

### 5.1 Entity

An entity refers to the subject of one or more claims.

The SDK MUST:

- Accept structured entity identifiers only.
- Preserve the semantic identity provided by the client.
- Normalize Unicode.
- Trim surrounding whitespace.
- Lowercase the entities if the identifier namespace is case-insensitive.
- Reject ambiguous entity identifiers.

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

### 5.2 Attribute

An attribute refers to a property of an entity.

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

### 5.3 Value

Values are canonicalized based on the underlying data type.

The SDK MUST:

- Normalize boolean values.
- Normalize numeric representations.
- Remove surrounding whitespaces for string values.
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
  
### 5.4 Units

Unit normalization is outside the scope of this specification.

Clients are responsible for converting measurements into deterministic units before invoking the Verity SDK.

## 6. Assertion Construction

### 6.1 Source

Each assertion MUST reference exactly one canonical source.

The source MUST satisfy the requirements specified in Section 4.

### 6.2 Claim

Each assertion MUST reference exactly one canonical claim.

The claim MUST satisfy the requirements specified in Section 5.

### 6.3 Assertion

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

## 7. Canonical Forms

Prior to generating linkage tokens, canonical sources, claims, and assertions MUST be serialized into deterministic JSON using the JSON Canonicalization Scheme as described in RFC 8785.

The serial representation MUST be consistent across compliant implementations.

### 7.1 Canonical Source

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

### 7.2 Canonical Claim

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

### 7.3 Canonical Assertion

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

## 8. Versioning

- Canonicalization specification versions

## 9. Conformance

- Requirements for compliant implementations
