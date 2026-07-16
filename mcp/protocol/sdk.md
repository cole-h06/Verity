# Verity SDK

## 1. Introduction

The Verity SDK provides a standardized interface for constructing credibility graphs and communicating with Verity deployments.

The SDK enables client applications to declaratively map structured data into canonical sources, claims, and assertions according to the Verity Protocol prior to generating privacy-preserving linkage tokens and submitting graph updates for credibility inference.

This document defines the responsibilities required to be compliant with Verity SDK implementations.

### Scope

This specification describes the behavior of the Verity SDK. The canonicalization rules referenced throughout this document are defined separately in the Verity Canonicalization Specification.

## 2. Design Goals

The Verity SDK is designed according to the following principles.

### Minimal Integration

The SDK integrates with existing data pipelines without requiring application-specific modifications to the Verity Protocol.

### Domain Agnostic

The SDK operates on structured assertions regardless of application domain.

### Deterministic

Equivalent structured inputs produce equivalent canonical representations across compliant SDK implementations.

### Language Independent

The SDK specification may be implemented in any programming language while preserving protocol compatibility.

## 3. Scope

The Verity SDK operates exclusively on structured assertions.

Responsibilities of the SDK include:

- Mapping structured data declaratively.
- Canonicalization according to the Verity Canonicalization Specification.
- Construction of the credibility graph.
- Generation of privacy-preserving linkage tokens.
- Communication with Verity deployments.

Responsibilities that fall outside the scope of the SDK include:

- Semantic extraction from unstructured data.
- Entity resolution.
- Information retrieval.
- LLM prompting.
- Agent orchestration.
- Data storage.

## 4. Responsibilities

The Verity SDK is responsible for converting structured assertions into graph updates in accordance with the Verity Protocol.

### 4.1 Declarative Mapping

The SDK provides a declarative mapping interface for mapping existing structured data into canonical sources, claims, and assertions.

Compliant SDK implementations MUST preserve the mappings defined by the client application and MUST NOT require changes to existing application-specific data models.

### 4.2 Canonicalization

The SDK MUST canonicalize mapped sources, claims, and assertions in accordance with the Verity Canonicalization Specification.

The SDK MUST reject any data which cannot be deterministically canonicalized.

### 4.3 Graph Construction

The SDK MUST construct graph updates based on the canonical sources, claims, and assertions.

The SDK MUST preserve the graph topology represented by the mapped assertions.

### 4.4 Linkage Generation

The SDK MUST generate privacy-preserving linkage tokens from canonical graph objects prior to transmission.

The SDK MUST ensure equivalent canonical representations produce equivalent linkage tokens.

### 4.5 Deployment Communication

The SDK MUST submit graph updates to compliant Verity deployments.

The SDK MUST deserialize credibility responses into structured results for the client application.

## 5. Integration Workflow

The Verity SDK is designed to be integrated into existing pipelines that extract structured data, but does not require any changes to the upstream extraction process or downstream application logic.

The SDK performs the following sequence of operations:

### 5.1 Existing Pipeline

The client application extracts structured assertions using its existing data processing pipeline.

### 5.2 Declarative Mapping

Structured data is declaratively mapped to sources, claims, and assertions.

### 5.3 Canonicalization

Mapped graph objects are canonicalized according to the Verity Canonicalization Specification.

### 5.4 Linkage Generation

Canonical graph objects are converted into privacy-preserving linkage tokens.

### 5.5 Graph Submission

The SDK submits the resulting graph update to a compliant Verity deployment.

### 5.6 Credibility Response

The Verity deployment returns credibility results to the client application.

## 6. Supported Inputs

The Verity SDK accepts structured data that can be deterministically mapped into sources, claims, and assertions.

Supported input formats include:

### 6.1 JSON Objects

Structured JSON objects and arrays.

### 6.2 Structured Language Objects

Language-native structured objects, such as:

- Classes
- Structs
- Records
- Pydantic models
- Dataclasses
- TypedDicts

### 6.3 Relational Data

Structured rows obtained from relational databases.

### 6.4 DataFrames

Tabular data stored as DataFrames.

### 6.5 Structured Serialization Formats

Structured serialization formats, such as:

- Protocol Buffers
- Apache Avro
- Apache Arrow

The SDK MAY support additional structured formats provided that they are deterministically mappable to canonical sources, claims, and assertions.

The SDK MUST reject unstructured inputs that require semantic extraction prior to graph construction.

## 7. Declarative Mapping

The Verity SDK supports a declarative mapping interface for converting existing structured data into canonical sources, claims, and assertions.

Declarative mappings define how fields from structured input are mapped to canonical sources, claims, and assertions without requiring custom application-specific transformation logic.

### 7.1 Mapping Schema

The mapping schema defines how input fields map to canonical sources, claims, and assertions.

### 7.2 Field Selection

Mappings MAY reference nested fields within structured inputs.

Verity SDK implementations MUST preserve the mapping defined by the client application.

### 7.3 Custom Transforms

Verity SDK implementations MAY support deterministic custom transforms prior to canonicalization.

Custom transformations MUST produce deterministic outputs for equivalent structured inputs.

Semantic extraction is outside the scope of the Verity SDK.

## 8. Graph Construction

The Verity SDK constructs graph updates from canonical sources, claims, and assertions.

### 8.1 Sources

The SDK constructs source nodes from canonical sources.

Equivalent canonical sources MUST resolve to the same source node.

### 8.2 Claims

The SDK constructs claim nodes from canonical claims.

Equivalent canonical claims MUST resolve to the same claim node.

### 8.3 Assertions

The SDK constructs directed assertions between source nodes and claim nodes.

Duplicate assertions MUST NOT appear within the same graph update.

## 9. Communication

The Verity SDK communicates with compliant Verity deployments according to the Verity Protocol.

### 9.1 Graph Submission

The SDK submits graph updates to a Verity deployment.

### 9.2 Credibility Response

The SDK deserializes credibility responses into structured objects for the client application.

## 10. Versioning

SDK implementations SHOULD declare the supported Verity Protocol version and Canonicalization Specification version.

SDK implementations MUST reject incompatible protocol versions.

## 11. Conformance

An implementation conforms to the Verity SDK Specification if it satisfies the requirements defined in this document and remains compatible with the Verity Protocol and Verity Canonicalization Specification.
