# Verity Protocol

## 1. Introduction

The Verity protocol describes the contract between clients and Verity deployments.

Verity computes structural credibility based on graphs built from sources, claims, and assertions, but does not interpret the underlying content. Clients extract structured assertions from their local data. Then, the graph is constructed and submitted to a Verity deployment for inference.

This document describes the responsibilities and guarantees required by the interoperable implementations of the Verity Protocol.

## 2. Terminology

This document uses the following terms:

- Source: The origin making one or more claims.
- Claim: A structured piece of information about an entity.
- Assertion: The relationship between a source and a claim.
- Credibility Graph: A bipartite graph composed of sources, claims, and assertions.
- Client: Software that constructs and submits graph updates.
- Verity Deployment: A self-hosted or cloud-hosted implementation of the Verity Protocol.

## 3. Design Goals

The Verity Protocol is built according to the following principles:

### Domain Agnostic

Verity operates on graph topology without any domain-specific semantics.

### Deterministic

Equivalent inputs result in equivalent graph structure.

### Privacy Preserving

Clients canonicalize assertions and convert them into privacy-preserving linkage tokens. Verity deployments do not require the underlying content in order to perform inference.

### Persistent

Each Verity deployment stores and maintains a persistent credibility graph that changes with new assertions.

## 4. Protocol Roles

### Client

The client MUST:

- Extract structured assertions from local data.
- Construct graph updates from the extracted assertions.
- Canonicalize graph updates according to the Verity Canonicalization Specification.
- Generate privacy-preserving linkage tokens from the canonicalized graph.
- Submit graph updates to a Verity deployment.

The Verity protocol does not support semantic extraction from unstructured data.

### Verity Deployment

A Verity Deployment MUST:

- Store and maintain the credibility graph.
- Resolve linkage tokens.
- Update graph topology.
- Compute structural credibility.
- Return deterministic credibility signals.

A Verity deployment MUST NOT interpret the underlying content.

A Verity deployment assumes every structured graph update is compliant with the protocol, so no semantic extraction is performed.

## 5. Protocol Overview

The protocol is composed of the following stages:

1.  Structured Extraction: Client obtains structured assertions from local sources.
2.  Canonicalization: Client deterministically canonicalizes extracted assertions.
3.  Linkage Generation: Client generates privacy-preserving linkage tokens from canonicalized assertions.
4.  Graph Construction: Client constructs graph update messages using linkage tokens.
5.  Graph Submission: Client transmits graph updates to a Verity Deployment.
6.  Credibility Inference: Verity Deployment computes credibility over the graph.
7.  Credibility Response: Verity Deployment returns credibility signals to the client.

The specific inference algorithm implementations are not specified here.

## 6. Protocol Guarantees

A conforming Verity Protocol guarantees the following:

- Equivalent canonicalized inputs produce equivalent graph structures.
- Credibility is derived solely from graph structure, not from the semantic interpretation of content.
- Inference results are deterministic for a given state of the credibility graph.
- Protocol compatibility is maintained even with future improvements to the inference algorithm used by a Verity Deployment.

## 7. Conformance

An implementation conforms to the Verity Protocol if and only if it adheres to all of the requirements defined in this document.

The Verity inference engine may be updated over time to improve the inference algorithms, provided these updates maintain the guarantees listed in section 6.
