# Chapter 3 — Traits and dynamic abstraction

[Specification index](../language-specification.md) · Previous: [2. Types and ownership](02-types-and-ownership.md) · Next: [4. Closures, captures, and scoped access](04-captures-and-access.md)

This chapter explains static trait selection and runtime trait packages, including the contracts that survive abstraction.

**Prerequisites:** [2. Types and ownership](02-types-and-ownership.md).

The numbered rules are normative under the [specification conventions](../language-specification.md). Examples are illustrative snippets; names and omitted bodies may stand for surrounding program or library context.

A trait can expose inspection without transferring ownership:

```eldude
trait Display {
    fn display(view self) -> Text;
}
```

## In this chapter

- [10. Traits](#10-traits)
- [11. Dynamic trait abstraction](#11-dynamic-trait-abstraction)

## 10. Traits

### 10.1 Coherent constrained polymorphism

Traits provide constrained polymorphism:

```eldude
trait Eq<T> {
    fn eq(left: T, right: T) -> Bool;
}
```

Resolution MUST follow the decidable rules of [§§10.6](#106-implicit-implementation-patterns-and-selection)–[10.8](#108-associated-equations-and-normalization) and MUST be independent of import order. Declarations outside that fragment are rejected even if a compiler could establish termination by another method. Runtime `diverge` never permits nonterminating static checking.

### 10.2 Implementation ownership

An implicit implementation MUST be declared in the module defining either:

- the trait; or
- the nominal head type.

This rule ensures a canonical implementation index compatible with direct-import separate compilation.

Overlapping implicit implementations are rejected using the head-only test of [§10.6](#106-implicit-implementation-patterns-and-selection); prerequisites do not disambiguate overlapping heads.

Alternative behavior uses explicit wrappers or dictionary values.

### 10.3 Associated types and GATs

Associated types and generic associated types are supported subject to the equation-admissibility and normalization rules of [§10.8](#108-associated-equations-and-normalization). Each implementation supplies one equation for each associated declaration, including every GAT. A GAT equation binds the declaration's additional parameters without separately specializing them; specialization is determined solely by the enclosing implementation head.

```eldude
trait Collection<C> {
    type Item;
}
```

### 10.4 Method lookup

Inherent methods live in `impl Type { ... }`. Trait methods are selected from deterministic statically known candidate sets.

Method-call syntax selects the receiver mode before name/type resolution:

```eldude
value.method(args)          // self
view value.method(args)     // view self
mut value.method(args)      // mut self
```

None of these forms searches arbitrary free functions. Ambiguity after ordinary deterministic candidate selection is an error. The parser does not inspect the selected method declaration to decide which form was written.

### 10.5 Receiver modes

Methods declare the same receiver modes as ordinary parameters:

```eldude
self
view self
mut self
```

A call must use the corresponding syntactic form from [§10.4](#104-method-lookup). `view` and `mut` on method calls establish the same call-scoped grants as explicit ordinary arguments; dot syntax does not implicitly create a grant. Access-prefixed receivers are bindings rather than arbitrary computed expressions, matching the non-reified access model. A consuming `self` call is written without an access prefix.

No receiver mode creates a first-class reference.

### 10.6 Implicit implementation patterns and selection

An implementation head consists of the canonical trait identity, its arguments, and the implementing receiver type. The receiver is either a nominal application or a type parameter; the implementation-ownership rule of [§10.2](#102-implementation-ownership) still applies. Head patterns are finite, kind-correct first-order applicative terms: parameters, canonical nominal/primitive constructor identities, and their applications, including tuple and monomorphic function-type constructors. They exclude `forall`, associated projections, and type-level computation. Named higher-kinded parameters may occur in applications; matching never synthesizes a type lambda. Transparent aliases are expanded first and recursive alias expansion is rejected.

Region, effect-row, capture-row, and natural slots in a head or searched prerequisite contain only a parameter or a canonical constant of that category. Natural constants are literal indices. Closed rows are treated as canonical constants; matching does not split rows or solve arithmetic equations. Constructor parameters range over named constructors or other constructor parameters, not partially applied associated families or computed type functions. These restrictions concern implicit matching, not ordinary annotated signatures.

Head overlap is decided by renaming both heads' parameters apart and applying kind-correct first-order unification, with an occurs check, to their receiver and trait-argument terms. Two heads for the same trait overlap exactly when that unification succeeds. All visible headers in the canonical index are checked, independent of import order and of their prerequisites. Conflicting headers are rejected at the module boundary that first brings them together.

Every generic parameter declared by an implicit implementation MUST occur in its receiver or trait arguments after alias expansion. This coverage rule applies to every generic category; prerequisites and associated-equation outputs cannot determine an otherwise absent parameter. Consequently `impl<T> Assoc for Foo { type Out = T; }` is rejected: matching `Assoc for Foo` supplies no value for `T`. Unused implementation parameters are removed rather than existentially guessed.

Selection uses one-way matching: only the implementation's parameters may be instantiated; the goal's abstract parameters and unresolved projections are rigid. Exact evidence in the local constraint environment is used first. Otherwise zero matching heads leaves an unsatisfied obligation, and one matching head is selected and its substituted prerequisites must all be discharged. Goals containing inference variables are postponed until ordinary inference fixes their relevant structure; they are never resolved by guessing an implementation. A remaining obligation must be supplied by a declared bound or is rejected at the checking boundary.

### 10.7 Decreasing implementation prerequisites

For a head or prerequisite, its argument terms include both the receiver and all trait arguments, excluding the trait name. Define `size` as the total number of nodes in their first-order applicative term trees: each parameter/constant and each application node counts once. Let `occurs(v, terms)` count occurrences of parameter `v` in those terms.

Every prerequisite generated by an implicit implementation, including intrinsic predicates and equalities, MUST be projection-free after alias expansion. Every user-trait prerequisite `P` of implicit implementation head `H` additionally MUST satisfy:

```text
size(P.arguments) < size(H.arguments)
for every parameter v: occurs(v, P.arguments) <= occurs(v, H.arguments)
P.arguments contain no associated projections or type-level computation
```

Aliases are expanded before these checks. Every parameter in a prerequisite must therefore occur in the head. Each prerequisite is checked independently; several smaller prerequisites are permitted. The same rule applies when the prerequisite names a different trait. This strict decrease is preserved by substitution of normalized terms, so mutually recursive trait declarations cannot create an infinite prerequisite chain.

Compiler-governed constraints such as `Dup`, `Discard`, and `NonAbandoning` use their intrinsic judgments, not user implementation search. They cannot introduce a dependency back into that search. Generic signatures may state explicit bounds involving projections; the prohibition above applies to prerequisites generated by implicit implementations. Trait-level bounds, where present, are expanded into each implementation's prerequisites before checking; recursive bound expansion is rejected.

For example, `Eq<List<T>>` requiring `Eq<T>`, or `Eq<Pair<A,B>>` requiring each component's `Eq`, decreases and is admitted. `Needs<List<T>>` requiring `Needs<List<List<T>>>`, and `A<T>` requiring `B<T>` on the same argument structure, are rejected. A prerequisite duplicating a parameter more often than the head is rejected even if its written size is smaller.

### 10.8 Associated equations and normalization

An associated projection is identified by its canonical trait/member, receiver, trait arguments, and any GAT arguments. Its equation's input terms are the enclosing implementation head's receiver and trait arguments followed by the GAT parameters. Associated-member names do not contribute to input size.

Every free variable of an associated equation's right-hand side and obligations MUST occur in these input terms; explicitly nested `forall` binders scope only their own bodies. Together with implementation coverage, this ensures that selecting an equation determines every substituted output variable.

For every further associated projection `Q` in an equation's right-hand side, its input terms MUST be projection-free and satisfy both `size(Q.inputs) < size(equation.inputs)` and the parameter-occurrence condition of [§10.7](#107-decreasing-implementation-prerequisites). Known acyclic aliases within the implementation are expanded before this check; recursive local associated aliases are rejected. Declared GAT-local bounds are expanded into each equation's obligations: all are projection-free after permitted alias expansion, and every user-trait obligation satisfies the same size/occurrence decrease against the equation's full input terms. The output may freely construct nominal types and repeat parameters outside further projection inputs. Changing the associated member or trait does not exempt a projection from decrease.

Thus the schematic equation `Flatten(List<T>) = List<Flatten(T)>` is admitted, while `Loop(T) = List<Loop(T)>` and `Loop(T) = Loop(List<T>)` are rejected. GAT arguments participate in the comparison, so shrinking a receiver while arbitrarily growing another argument does not establish decrease.

Normalization is deterministic: normalize projection inputs from left to right, select the unique equation by [§10.6](#106-implicit-implementation-patterns-and-selection), substitute its inputs, and normalize the resulting type from left to right. Equation selection records the enclosing implementation's trait obligation and substituted prerequisites; all obligations must be discharged before the type is accepted. An equation is not permission to erase an unsatisfied bound. All implementation-generated prerequisites and GAT-local bounds are projection-free ([§10.7](#107-decreasing-implementation-prerequisites)), so equation reduction may generate trait obligations but recursive trait search cannot generate fresh projection computations.

A projection with an abstract receiver and no applicable equation remains an opaque, kinded term. Equality may use an explicit associated equality supplied by the local contract, or compare identical opaque terms; it MUST NOT infer a receiver or implementation by inverting an associated equation. Explicit equality substitutions require an occurs check and acyclic expansion, including occurrences beneath projections. No recursive equality expansion is permitted. A stuck projection is not itself an error, but a required equality not established by these rules is rejected.

This establishes finite normalization and prerequisite search for admitted declarations. Implementations may cache results or change evaluation scheduling while preserving these decisions. A compiler-specific depth/fuel limit is a resource limit, not an alternative language-admissibility rule.

## 11. Dynamic trait abstraction

### 11.1 `any Trait`

`any Trait` is an explicit runtime-dispatched package.

```eldude
any Parser<Token = Token>
```

Creating such a package is explicit; there is no universal implicit coercion.

### 11.2 Dynamic compatibility

Dynamic compatibility is a closed static judgment over the erased package interface. Write conceptually:

```text
StaticEnvironment ⊢ DynCompatible(any Trait<Args... associated bindings ...>)
```

The judgment is decided from the canonical interface of the trait plus the package's visible arguments/bindings. Imported implementation bodies are never consulted. Because Eldude has no syntax for excluding individual trait methods from dynamic dispatch, every method of the trait must satisfy the method rule below; otherwise that `any Trait<...>` type is ill-formed.

For a candidate package interface `P = any Trait<...>`, each trait method `m` is dynamically compatible exactly when all of the following hold after substituting the trait arguments and package associated-type bindings supplied by `P`:

1. `m` has exactly one ordinary Eldude receiver: `self`, `view self`, or `mut self`.
2. `m` declares no method-local generic parameter of any Eldude generic category (`Type`, type constructor, `Region`, `EffectRow`, `CaptureRow`, or `NatIndex`). A higher-rank value type nested inside an otherwise closed parameter/result type is permitted; the prohibition is on generic parameters introduced by the dynamically dispatched method itself.
3. The distinguished concrete type variable `Self` occurs nowhere in the substituted callable contract except as the receiver. In particular, a parameter or result whose type is raw `Self` is not dynamically compatible.
4. No GAT projection occurs in the substituted callable contract.
5. Every ordinary associated-type projection used by a parameter, result, constraint, effect/capture relation, or other client-visible part of the callable contract is fixed by the package interface or canonically reduces to a package-visible type. No unresolved associated projection remains after substitution.
6. Every method-specific static constraint remaining after substitution is provable from the package interface alone. Dynamic invocation does not introduce an additional trait-search obligation whose truth depends on discovering the hidden concrete `Self`.
7. The method's parameter/result types, effect row, continuation-control envelope, and result-capture bound are well formed using only package-visible static information, ordinary argument/capture variables, and the abstract capture/provenance summary of the receiver package. They MUST NOT refer to the hidden concrete nominal identity, representation, or a hidden `Self`-specific static fact.

These conditions define `DynCompatible`; there is no additional implementation-defined notion of “supported” or “representable”. A trait that fails them may still be used statically. Code needing runtime erasure must instead use a dyn-compatible trait, an explicit wrapper/dictionary, or nominal opacity.

Examples:

```eldude
trait Source {
    type Item;
    fn next(mut self) -> Option<Self::Item>;
}

// Potentially well formed when Item is fixed:
any Source<Item = Token>
```

The empty row of `next` permits in-place advancement through its supplied `mut self` grant and admits no additional effects ([§14.3](04-captures-and-access.md#143-mut)). A direct call forming a root grant to an erased mutable owner charges that owner's region state; dispatch through an existing projected grant preserves its supplied authority. Neither rule requires inspecting the hidden implementation body.

An implementation of this empty-row `Source::next` MUST be valid for every admissible supplied grant, including projection from a different owner/region. Advancement that requires an independent state identity's effect is incompatible with this method contract and MUST be rejected. For example, placing an erased owner tied to `@s` inside an array in `@r` does not let its implementation mutate independent `@s` state under an empty row using the projected `@r` authority. Supporting that behavior requires the state effect in the trait's public callable contract; retained package provenance does not substitute for it.

After substituting `Item = Token`, the method exposes no concrete `Self` outside the receiver. By contrast:

```eldude
trait CopyOut {
    fn copy(view self) -> Self;
}

trait GenericMap {
    type Item;
    fn map<U>(view self, f: fn(Self::Item) -> U) -> List<U>;
}
```

`any CopyOut` is ill-formed because `Self` remains in the result, and `any GenericMap` is ill-formed because `map` introduces the method-local type parameter `U`. A trait method that exposes a GAT projection is likewise statically callable but makes the trait ineligible for `any` in the core.

A dynamically callable `mut self` method does not make every erased package a root mutable owner. Direct root `mut` access to the package is available only when packaging preserves compiler-recognized mutable-owner status/provenance; a package reached through an existing projected `mut` grant may use that derived grant normally.

### 11.3 Usage guarantees

A bare `any Trait` makes no `Dup` or `Discard` promise and is conservatively non-duplicable and non-discardable.

Stronger erased values state guarantees explicitly:

```eldude
any Source + Discard
any Source + Dup + Discard
```

Packaging checks the hidden concrete value against the advertised predicates.

A bare `any Trait` is an ownership-bearing erased package and may itself be a linear obligation. APIs intended for general heterogeneous storage or results that callers may abandon SHOULD request `+ Discard` explicitly. A public API returning a non-`Discard` erased package SHOULD expose an evident consuming or discharge operation; tooling SHOULD warn when an exported erased obligation appears to have no usable consumption path. This guidance is ergonomic and does not add another static permission predicate.

### 11.4 Erasure preserves obligations

Erasure hides the concrete nominal type and representation only.

It MUST preserve, in the static package contract:

- usage guarantees;
- capture/provenance obligations;
- region retention;
- required associated-type equalities;
- effects and result-capture bounds of dynamically callable methods;
- mutable-owner status/provenance when a dynamically callable `mut self` method requires it.

`any` cannot be used to hide a region escape, taskgroup provenance, or resource obligation.

---

[Specification index](../language-specification.md) · Previous: [2. Types and ownership](02-types-and-ownership.md) · Next: [4. Closures, captures, and scoped access](04-captures-and-access.md)
