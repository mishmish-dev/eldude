# Eldude Formal Grammar

**Status:** normative syntax with an implemented recognizer; source execution covers a subset.

This complete grammar covers ordinary Eldude source and generated canonical semantic interfaces. It is generated from [eldude.ebnf](eldude.ebnf), the parsing clauses in [Foundations and programs](language-spec/01-foundations.md), and the interface clauses in [Interfaces, compilation, and tooling](language-spec/12-interfaces-and-tooling.md). Numbered references retain their identifiers in the [language specification](language-specification.md). The [manifesto](index.md#the-eldude-manifesto) describes the design principles.

The machine-readable forms are the EBNF artifact and [eldude-grammar.json](eldude-grammar.json), which contains normalized BNF, lexical rules, and parsing conventions. Syntax acceptance does not establish typing, visibility, usage, effects, termination, exhaustiveness, or audited native validity. Those judgments remain in the language specification.

## Entry points and notation

`source_file` parses an ordinary file, beginning with exactly one `module path;` declaration. `interface_file` parses generated canonical interfaces and additionally permits `semantic` blocks. The interface-only productions are unreachable from `source_file`; generated native contracts are not source annotations.

In EBNF, `::=` defines a production, `|` selects an alternative, parentheses group, `?` means zero or one, `*` means zero or more, and `+` means one or more. A sequence matches left to right. JSON strings quote exact terminals and regular expressions. Unquoted names reference productions or lexical token categories. An empty sequence matches no tokens. `#` starts a whole-line artifact comment.

`%token NAME = "regex";` defines a lexical category, `%skip NAME = "regex";` defines trivia, and `%keywords "words";` excludes reserved words from `IDENT`. Regexes use Python's `re` syntax without additional flags. Skip rules are considered in declaration order before token recognition. Otherwise choose the longest lexical match; ties prefer token categories in declaration order before punctuation. Reserved identifier lexemes become keyword tokens. Literal productions match exact spelling; lexical-category productions match category. Punctuation comes from the selected entry point's reachable literal vocabulary, so interface-only compound words do not alter ordinary source lexing. There is no implicit end-of-file token: the selected entry point must consume the entire token stream.

## Reserved words, sigils, and tokens

The source grammar reserves the following words because they participate directly in Eldude syntax:

```text
affine any as assert await break captures case const continue
effect else enum extern false fn for forall forward handle handler if impl
import in intrinsic let linear match module mut once pub region resume return self spawn
struct suspend taskgroup trait true try type unsafe using view where while
diverge
```

`with`, `tail`, and `state` are contextual words: they introduce handler composition, tail-resumption declarations, and region-state row entries in those specific grammatical positions, and are ordinary identifiers elsewhere. This permits projection APIs named `with`, record fields named `tail`, and values named `state` without name-dependent parsing.

`many`, `abort`, `error`, and `host` are not reserved words. Many-shot resumption is deferred; abortive operations are expressed by `affine ... -> Never`; expected-error composition uses nominal enums; host selection is root/build metadata rather than source syntax. Primitive type names such as `Int`, `Bool`, and `Unit` are ordinary predefined type names rather than keywords.

The category sigils are context-free tokens:

```text
!e     effect-row generic parameter declaration
@r     region identity/reference
#N     compile-time-natural generic parameter declaration
..C    capture-row parameter/rest
```

At expression level, `!Qualified::op(...)` is algebraic operation dispatch. `!` is not an ordinary general-purpose prefix operator. This prevents `!Console::check()` from having a second parse as boolean negation of an ordinary call.

Lexing uses longest-token matching for multi-character punctuation, including at least:

```text
::  ->  =>  .?  ??  ..  ==  !=  <=  >=
```

Turbofish is parsed as `::` followed by `<...>`; it is not a distinct semantic token. Nested generic closers are individual `>` tokens; Eldude defines no `>>` shift operator.

## Lexical payloads and source forms

Source is UTF-8. Identifiers use ASCII letters/underscore followed by ASCII letters/digits/underscores; capitalization does not create a second token category. Reserved words cannot be identifiers. `//` comments end at a newline or end of file; `/* ... */` comments are non-nesting. Whitespace/comments separate tokens except within literals. Numeric token forms are those of [§6.1.3](language-spec/02-types-and-ownership.md#613-numeric-literals-and-defaulting) and the artifact.

Double-quoted strings contain Unicode scalar values. Single-quoted character literals contain exactly one scalar value. Raw control characters U+0000–U+001F, unescaped delimiters/backslash, and literal newlines are excluded. Escapes are `\n`, `\r`, `\t`, `\0`, `\\`, `\"`, `\'`, and `\u{H}` with one to six hexadecimal digits representing a Unicode scalar value. Invalid scalar escapes are rejected. There are no raw, multiline, interpolated, or byte-string literal forms. String literals have type `Text`; character literals have type `Char`.

Anonymous function parameters may omit a type when ordinary inference or an expected function type supplies it, as in `fn(x) => x`. Named-function parameters are typed; receiver `self` uses its enclosing implementation/trait type. `forall<...>. Type` is the explicit higher-rank type form. An associated projection may use `T::Item` when its trait is unambiguous in the static contract, or `<T as Trait<Args>>::Item<GatArgs>` for explicit qualification. This is type syntax, not expression-level conversion.

Enum variants may use tuple payloads or nominal record payloads, for example `Cons { head: T, tail: LinkedList<T> }`; that record belongs to the enum constructor and is not a structural record type. Construction and patterns use `LinkedList::Cons { head, tail }`. All fields of an owned product/record pattern must be explicit, including wildcards; there is no rest pattern. Every nonfinal expression, including `while` and `for`, requires a terminating semicolon. A final loop expression may omit it and yields `Unit`. Thus `{ while condition {} ; -1 }` has an integer tail; without the separator, `{ while condition {} -1 }` is one subtraction expression and fails typing because its left operand is `Unit`.

## Operators and precedence

The following table is normative for parsing. It fixes association only; typing and evaluation behavior remain governed by the corresponding semantic/primitive contracts. Higher rows bind more tightly. User-defined operators and precedence do not exist.

| Level | Forms | Associativity / note |
|---|---|---|
| Postfix | call `(...)`, member `.name`, optional member `.?name`, indexing `[expr]`, turbofish `::<...>`, postfix `?` | left/postfix |
| Access-method call | `view receiver.method(...)`, `mut receiver.method(...)` | prefix applies to exactly the following method call |
| Numeric prefix | unary `+`, `-` | right; operand includes postfix operations |
| Multiplicative | `*`, `/`, `%` | left |
| Additive | `+`, `-` | left |
| Relational | `<`, `<=`, `>`, `>=` | non-associative |
| Equality | `==`, `!=` | non-associative |
| Coalescing | `??` | right |

`!Qualified::op(...)`, `await`, `spawn`, `unsafe { ... }`, `try { ... }`, `handle { ... } with handler ...`, `region name { ... }`, `using (...) { ... }`, and `taskgroup { ... }` are grammar-level expression forms rather than entries in the ordinary operator precedence ladder.

Angle brackets after a type path belong to the type grammar. Expression-level generic application requires turbofish, so parsing `a < b` never depends on discovering whether `a` names a generic function.

## Parsing and derivation selection

The normative grammar is context-free and defined by [eldude.ebnf](eldude.ebnf), published in the standalone [formal grammar](formal-grammar.md). The following disambiguation rules are part of that contract:

- `value.method(args)` selects a consuming/value receiver (`self`);
- `view value.method(args)` selects `view self`;
- `mut value.method(args)` selects `mut self`;
- `view`/`mut` access arguments and access-prefixed method receivers apply to an in-scope binding (including a callback parameter carrying a projected grant), not to an arbitrary computed expression; compute an expression into a binding first when access must be granted to its result;
- this binding-only rule keeps `f(view x.method())` unambiguous: it is a plain argument whose expression is the `view self` method call, while `f(view x)` is an ordinary `view` argument;
- the parser chooses among the three method forms syntactically, before method lookup; the type checker later verifies that the selected method has the matching receiver mode;
- `!path::op(args)` is always algebraic operation dispatch; explicit family arguments use `!path::<Args>::op(args)`, with the same expression-level turbofish convention as ordinary generic application;
- `@name`, `#name`, `!name` in generic-parameter lists, and `..name` in capture-row positions are determined solely by grammatical context;
- an effect row has fixed entries followed by at most one `| name` tail; `{| e}` is tail-only, and `{E | e}` extends that tail. Whether a fixed entry denotes an effect family rather than a row variable is checked by kinding, not parsing;
- `semantic { ... }` is not ordinary source syntax; it belongs to the `interface_file` entry point of the normative grammar;
- an unparenthesized nominal construction is excluded from the outer condition/scrutinee/source expression of `if`, `while`, `match`, and `for`; parentheses permit it and prevent confusion with the following block;
- `await` and `spawn` take the immediately following unary/postfix operand; use parentheses or a block to group a larger computation;
- an undelimited `=>` lambda body and the operand of `return` consume the longest following expression permitted by the enclosing grammatical delimiters. Among complete derivations, compare those body/operand end-token positions in order of their introducing `=>`/`return` tokens, earliest first, and choose the lexicographically greatest vector. Thus `fn(x) => x + 1` keeps the addition inside the lambda and `return f() + 1` returns the sum. Parenthesize the lambda/return expression when a following postfix/binary operation belongs outside it, as in `(fn(x) => x)(1)`;
- a capture clause attaches to the nearest unparenthesized function contract; parenthesize a returned function type before writing a capture clause for the outer function;
- a generic closing `>` immediately followed by `=` forms the longest token `>=`; separate them with whitespace when a closing delimiter and equality/initializer token are intended.

These rules select association among grammar derivations using syntax alone. The conformance recognizer checks token-stream membership and does not construct an AST or perform derivation selection; compiler parsers must also implement the stated association rules.

## Complete lexical and syntactic grammar

<!-- BEGIN GENERATED ELDUDE GRAMMAR -->
```ebnf
# Normative Eldude EBNF. Generated presentations: the Formal Grammar and JSON export.
# EBNF: ::= definition; | choice; () grouping; ? optional; * repetition; + one or more.
# JSON strings quote terminals and lexical regular expressions; # begins a whole-line comment.
%skip SPACE = "[ \\t\\r\\n]+";
%skip LINE_COMMENT = "//[^\\r\\n]*";
%skip BLOCK_COMMENT = "/\\*(?:[^*]|\\*(?!/))*\\*/";
%token FLOAT_LITERAL = "(?:[0-9](?:_?[0-9])*\\.[0-9](?:_?[0-9])*(?:[eE][+-]?[0-9](?:_?[0-9])*)?|[0-9](?:_?[0-9])*[eE][+-]?[0-9](?:_?[0-9])*)(?:f32|f64)?|[0-9](?:_?[0-9])*(?:f32|f64)";
%token INT_LITERAL = "(?:0b[01](?:_?[01])*|0o[0-7](?:_?[0-7])*|0x[0-9a-fA-F](?:_?[0-9a-fA-F])*|[0-9](?:_?[0-9])*)(?:i8|i16|i32|i64|i128|u8|u16|u32|u64|u128|int|uint|nat)?";
%token STRING_LITERAL = "\"(?:[^\"\\\\\\x00-\\x1f]|\\\\(?:[\"\\'\\\\nrt0]|u\\{[0-9a-fA-F]{1,6}\\}))*\"";
%token CHAR_LITERAL = "'(?:[^'\\\\\\x00-\\x1f]|\\\\(?:[\"\\'\\\\nrt0]|u\\{[0-9a-fA-F]{1,6}\\}))'";
%token IDENT = "[A-Za-z_][A-Za-z_0-9]*";
%keywords "affine any as assert await break captures case const continue effect else enum extern false fn for forall forward handle handler if impl import in intrinsic let linear match module mut once pub region resume return self spawn struct suspend taskgroup trait true try type unsafe using view where while diverge";

# Files and declarations
source_file ::= "module" path ";" module_item*;
module_item ::= import_decl | declaration;
import_decl ::= "pub"? "import" path "::" "{" import_names "}" ";";
import_names ::= import_name ("," import_name)* ","?;
import_name ::= IDENT ("as" IDENT)?;
declaration ::= "pub"? (function_decl | let_decl | struct_decl | enum_decl | trait_decl | effect_decl | alias_decl) | impl_decl | extern_block;
function_decl ::= "unsafe"? "fn" IDENT generic_params? parameters result_contract where_clause? (block | ";");
let_decl ::= "let" pattern (":" type)? "=" expr ";";
struct_decl ::= usage_modifier? "struct" IDENT generic_params? where_clause? ("{" fields? "}" | ";");
usage_modifier ::= "linear" | "affine";
fields ::= field_decl ("," field_decl)* ","?;
field_decl ::= "pub"? IDENT ":" type;
enum_decl ::= usage_modifier? "enum" IDENT generic_params? (where_clause? "{" variants? "}" | "where" "{" gadt_constructors? "}");
variants ::= variant ("," variant)* ","?;
variant ::= "pub"? IDENT ("(" type_list? ")" | "{" fields? "}")?;
gadt_constructors ::= gadt_constructor ("," gadt_constructor)* ","?;
gadt_constructor ::= "pub"? IDENT ":" type;
trait_decl ::= "intrinsic"? "trait" IDENT generic_params? where_clause? "{" trait_member* "}";
trait_member ::= method_decl | associated_decl;
method_decl ::= "unsafe"? "fn" IDENT generic_params? parameters result_contract where_clause? (block | ";");
associated_decl ::= "type" IDENT generic_params? where_clause? ";";
associated_equation ::= "type" IDENT generic_params? where_clause? "=" type ";";
impl_decl ::= "impl" generic_params? type ("for" type)? where_clause? "{" impl_member* "}";
impl_member ::= "pub"? method_decl | associated_equation;
effect_decl ::= "effect" IDENT generic_params? "{" effect_operation* "}";
effect_operation ::= ("tail" | "once" | "affine") IDENT parameters "->" type ";";
alias_decl ::= "type" IDENT generic_params? "=" type ";";
extern_block ::= "extern" STRING_LITERAL "{" ("pub"? function_decl)* "}";
parameters ::= "(" (parameter ("," parameter)* ","?)? ")";
parameter ::= access_mode? binding_name ":" type | access_mode? "self";
access_mode ::= "view" | "mut";
binding_name ::= IDENT | "self";
result_contract ::= "->" effect_row? type capture_clause?;
where_clause ::= "where" constraint ("," constraint)* ","?;
constraint ::= constraint_subject ":" constraint_bounds | type "=" type;
constraint_subject ::= type | ".." IDENT;
constraint_bounds ::= type ("+" type)*;

# Types, binders, and category slots
path ::= path_part ("::" path_part)*;
path_part ::= IDENT | "self";
generic_params ::= "<" generic_param ("," generic_param)* ","? ">";
generic_param ::= IDENT ("<" placeholders ">")? | "@" IDENT | "!" IDENT | ".." IDENT | "#" IDENT;
placeholders ::= "_" ("," "_")*;
type ::= forall_type | function_type | raw_pointer_type | any_type | tuple_type | applied_path | qualified_projection;
forall_type ::= "forall" generic_params "." type;
function_type ::= "fn" "(" (mode_type ("," mode_type)* ","?)? ")" result_contract;
mode_type ::= access_mode? type;
raw_pointer_type ::= "*" ("const" | "mut") type;
any_type ::= "any" applied_path ("+" applied_path)*;
tuple_type ::= "(" ")" | "(" type "," (type ("," type)* ","?)? ")" | "(" type ")";
applied_path ::= path type_args? ("::" IDENT type_args?)*;
qualified_projection ::= "<" type "as" applied_path ">" "::" IDENT type_args?;
type_args ::= "<" type_arg ("," type_arg)* ","? ">";
type_arg ::= type | region_ref | effect_row | capture_set | ".." IDENT | nat_expr | IDENT "=" type;
type_list ::= type ("," type)* ","?;
region_ref ::= "@" IDENT;
effect_row ::= "{" (effect_entries ","? | effect_entries? "|" IDENT)? "}";
effect_entries ::= effect_entry ("," effect_entry)*;
effect_entry ::= applied_path | "suspend" | "diverge";
capture_clause ::= "captures" capture_set;
capture_set ::= "{" (capture_entry ("," capture_entry)* ","?)? "}";
capture_entry ::= region_ref | ".." IDENT | path;
nat_expr ::= nat_product ("+" nat_product)*;
nat_product ::= nat_atom ("*" nat_atom)*;
nat_atom ::= INT_LITERAL | IDENT | "(" nat_expr ")";

# Expressions and fixed precedence
# Undelimited lambda bodies/return operands take the longest expression under §2.8.
expr ::= coalesce_expr;
coalesce_expr ::= equality_expr ("??" coalesce_expr)?;
equality_expr ::= relational_expr (equality_op relational_expr)?;
equality_op ::= "==" | "!=";
relational_expr ::= sum_expr (relational_op sum_expr)?;
relational_op ::= "<" | "<=" | ">" | ">=";
sum_expr ::= product_expr (("+" | "-") product_expr)*;
product_expr ::= unary_expr (("*" | "/" | "%") unary_expr)*;
unary_expr ::= ("+" | "-" | "await" | "spawn") unary_expr | postfix_expr;
postfix_expr ::= primary postfix*;
postfix ::= arguments | "." IDENT | ".?" IDENT | turbofish | "?" | "[" expr "]";
turbofish ::= "::" type_args;
arguments ::= "(" (argument ("," argument)* ","?)? ")";
argument ::= access_mode binding_name | expr;
primary ::= literal | path | struct_literal | tuple_expr | list_literal | lambda | block | if_expr | match_expr | while_expr | for_expr | scoped_expr | using_expr | handle_expr | access_method | operation_call | resume_expr | exit_expr;
literal ::= INT_LITERAL | FLOAT_LITERAL | STRING_LITERAL | CHAR_LITERAL | "true" | "false";
struct_literal ::= path "{" value_fields? "}";
value_fields ::= value_field ("," value_field)* ","?;
value_field ::= IDENT (":" expr)?;
tuple_expr ::= "(" ")" | "(" expr "," (expr ("," expr)* ","?)? ")" | "(" expr ")";
list_literal ::= "[" (expr ("," expr)* ","?)? "]";
lambda ::= "fn" "(" (lambda_param ("," lambda_param)* ","?)? ")" ("=>" expr | result_contract? block);
lambda_param ::= access_mode? binding_name (":" type)?;
block ::= "{" statement* expr? "}";
statement ::= let_decl | "assert" expr ";" | expr ";";
if_expr ::= "if" condition_expr block ("else" (block | if_expr))?;
match_expr ::= "match" condition_expr "{" match_arm* "}";
match_arm ::= "case" pattern ("if" condition_expr)? "=>" expr ";";
while_expr ::= "while" condition_expr block;
for_expr ::= "for" pattern "in" condition_expr block;
scoped_expr ::= "region" IDENT block | ("try" | "taskgroup" | "unsafe") block;
using_expr ::= "using" "(" acquisition ("," acquisition)* ","? ")" block;
acquisition ::= binding_name "=" expr;
access_method ::= access_mode binding_name "." IDENT turbofish? arguments;
operation_call ::= "!" path ("::" type_args "::" IDENT)? arguments;
resume_expr ::= "resume" arguments;
exit_expr ::= "return" expr? | "break" | "continue";
handle_expr ::= "handle" block "with" (IDENT "=")? "handler" applied_path "{" handler_clause* "}";
handler_clause ::= IDENT "(" patterns? ")" "=>" expr ";"? | "return" pattern "=>" expr ";"? | "forward" (IDENT | "..") ";";

# Control conditions exclude an unparenthesized nominal literal at the outer level.
condition_expr ::= condition_equality ("??" condition_expr)?;
condition_equality ::= condition_relation (equality_op condition_relation)?;
condition_relation ::= condition_sum (relational_op condition_sum)?;
condition_sum ::= condition_product (("+" | "-") condition_product)*;
condition_product ::= condition_unary (("*" | "/" | "%") condition_unary)*;
condition_unary ::= ("+" | "-" | "await" | "spawn") condition_unary | condition_primary postfix*;
condition_primary ::= literal | path | tuple_expr | list_literal | lambda | block | if_expr | match_expr | while_expr | for_expr | scoped_expr | using_expr | handle_expr | access_method | operation_call | resume_expr | exit_expr;

# Owned and inspection patterns share syntax; typing determines ownership.
pattern ::= pattern_atom ("|" pattern_atom)*;
pattern_atom ::= "_" | signed_literal | path ("(" patterns? ")" | "{" pattern_fields? "}")? | tuple_pattern;
signed_literal ::= ("+" | "-")? (INT_LITERAL | FLOAT_LITERAL) | STRING_LITERAL | CHAR_LITERAL | "true" | "false";
tuple_pattern ::= "(" ")" | "(" pattern "," (pattern ("," pattern)* ","?)? ")" | "(" pattern ")";
patterns ::= pattern ("," pattern)* ","?;
pattern_fields ::= pattern_field ("," pattern_field)* ","?;
pattern_field ::= IDENT (":" pattern)?;

# Distinct generated canonical interfaces. These productions are unreachable from source_file.
interface_file ::= "module" path ";" interface_item*;
interface_item ::= import_decl | declaration semantic_block?;
semantic_block ::= "semantic" "{" semantic_clause* "}";
semantic_clause ::= "result-captures" "<=" capture_bound ";" | "mutable-owner-region" "=" region_ref ";" | "finite-positive-parameters" "=" "{" index_list? "}" ";" | "finite-iteration" "=" "true" ";" | "representation" "=" ("opaque" | "complete") ";" | "usage" "{" "Dup" "=" usage_condition ";" "Discard" "=" usage_condition ";" "}" | ffi_contract | ffi_protocol | semantic_selector "{" semantic_clause* "}";
usage_condition ::= "true" | "false" | usage_conjunction ("|" usage_conjunction)*;
usage_conjunction ::= "(" constraint ("," constraint)* ")";
index_list ::= INT_LITERAL ("," INT_LITERAL)*;
capture_bound ::= "{" (generated_capture ("," generated_capture)* ","?)? "}";
generated_capture ::= "captures" "(" (binding_name | "parameter" "(" INT_LITERAL ")" | "..") ")" | capture_entry;
semantic_selector ::= "parameter" "(" INT_LITERAL ")" | "result" | "member" "(" path ")" | "component" "(" INT_LITERAL ")";

# Generated audited native contracts; scope/value consistency is checked semantically.
ffi_contract ::= "ffi-contract" "{" ffi_clause* "}";
ffi_protocol ::= "ffi-protocol" path "=" STRING_LITERAL ";";
ffi_clause ::= ffi_property "=" ffi_value ";" | ffi_subject "{" ffi_clause* "}";
ffi_subject ::= semantic_selector | "pointer" | "output" | "callback" | "marshalling";
ffi_property ::= "invocation" | "blocking" | "finite-return" | "native-cancellation" | "foreign-unwind" | "ownership" | "retention" | "mutability" | "aliasing" | "stable-address" | "provenance" | "initialization" | "failure-state" | "lifetime" | "cardinality" | "reentrancy" | "thread-affinity" | "delivery-domain" | "barrier" | "suspension" | "algebraic-crossing" | "cancellation" | "defect" | "pending-defect-entry" | "deregistration" | "drain" | "undelivered" | "shutdown" | "preconditions";
ffi_value ::= IDENT | capture_bound | "protocol" "(" path ")";
```
<!-- END GENERATED ELDUDE GRAMMAR -->

## Generated semantic clauses

Every client-validity fact in the canonical semantic interface MUST have a deterministic human-readable rendering produced by the standard toolchain. Facts already expressible in ordinary Eldude syntax use that syntax. Client-relevant inferred facts that have no ordinary author-written spelling use a generated `semantic { ... }` block rather than opaque solver variables.

Representative generated clauses are:

```text
semantic {
    representation = opaque;
    usage { Dup = (T: Dup); Discard = (T: Discard); }
    result-captures <= {captures(cell), ..C, @r};
    mutable-owner-region = @r;
    finite-positive-parameters = {0, 1};
}
```

These clauses illustrate separate applicable subjects, not one declaration requiring every fact. `result-captures <= {...}` is the authoritative public upper-bound algebra of [§13.6](language-spec/04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation). `mutable-owner-region = @r` states the intrinsic `MutableOwner<T,@r>` fact when clients may form root `mut` grants. `finite-positive-parameters` lists the zero-based generic parameter positions certified by [§8.5](language-spec/02-types-and-ownership.md#85-finite-inductive-recursive-declarations); `{}` certifies no positions. `finite-iteration = true` applies only to a concrete `Iterator` implementation certified under [§35.5](language-spec/08-collections.md#355-finite-iteration-and-non-divergence); omission offers no finite-completion guarantee. Storage positivity and finite iteration are distinct facts. FFI facts use the generated contracts and protocol descriptions of [§72.9](language-spec/12-interfaces-and-tooling.md#729-generated-ffi-semantic-contracts).

Capture bounds use whole values only ([§13.6](language-spec/04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation)). Mutable arguments use the uniform conservative post-call rule; no per-callable mutation or stored-payload contract is exported. A capture-free return such as `Unit` does not suppress those mutation checks.

`representation = complete` certifies that the rendered nominal fields/constructors are exhaustive. `representation = opaque` states that they are incomplete or unavailable: struct construction/decomposition cannot infer missing fields, and enum matching must account for the opaque remainder of [§5.3](language-spec/01-foundations.md#53-exports-and-opacity). A semicolon struct implies `opaque`; a generated braced nominal declaration with omitted members MUST carry the marker. In the absence of a marker, a braced declaration is complete. An explicit contradictory marker is an interface error. Private member names and types are not serialized merely to explain this fact.

A generated `usage` block gives each intrinsic permission's public sufficient condition. `true` offers the permission unconditionally; `false` offers no such guarantee. A parenthesized comma-separated set of constraints is conjunction, and `|` between those sets is disjunction. The only permitted atoms are kind-correct public type equalities and intrinsic `Dup`/`Discard` bounds on types or capture rows. The condition may mention only the nominal declaration's public generic inputs and publicly nameable types; it introduces no user trait search, negative predicate, existential guess, or executable proof. A client gains a permission when at least one conjunction is established by the existing equality/usage judgments. Recursive conditions must be justified by the existing structural usage derivation, never by assuming the permission being established.

For example, an opaque `Box<T>` that stores `T` publishes `usage { Dup = (T: Dup); Discard = (T: Discard); }`, whereas a phantom representation may publish both permissions as `true`; a linear resource publishes both as `false`. These are permission conditions, not formation constraints: `Box<LinearResource>` remains a legal linear type. The defining module checks every offered condition against its representation and source-level strengthening. Opaque declarations MUST publish both conditions; unavailable hidden proofs may conservatively withhold a guarantee, but cannot grant one. Complete representations may derive the same facts directly. An interface usage block is not an `impl Dup`/`impl Discard` declaration and is unreachable from ordinary source. Changing a published condition changes the semantic interface.

Other future generated clauses MUST use source-level semantic terminology and MUST NOT expose implementation-specific solver state as the only representation of a client-relevant fact.

A semantic block is attached to its preceding declaration. Nested `member(path) { ... }` clauses select individual methods, fields, associated declarations, or enum constructors by canonical identity; this includes trait and implementation methods and declarations in an `extern` block. Nested `parameter(n)`, `result`, and `component(n)` clauses select callable slots and stored tuple/payload components with the same zero-based rules as [§72.9](language-spec/12-interfaces-and-tooling.md#729-generated-ffi-semantic-contracts). They remain available for nested callable, usage, and FFI contracts, but do not refine stored-value capture summaries. `result-captures` applies only to a callable subject and bounds that callable's whole result. Repeated selectors or facts in the same scope, invalid member/slot identities, or facts inappropriate to that subject are interface errors. Selectors use [§72.9](language-spec/12-interfaces-and-tooling.md#729-generated-ffi-semantic-contracts)'s canonical recursive ordering.

Within a selected callable contract, `captures(x)` refers to the whole named parameter/accessed-value summary. The positional spelling `captures(parameter(n))` refers to its zero-based parameter summary (counting a receiver), and `captures(..)` refers to the whole callable environment. Sources have no projection suffix. Canonical rendering uses positional parameter sources. Selecting a nested callable starts a new parameter/environment scope; its bound describes its own return, and cannot refer implicitly to the enclosing callable's arguments. The bound's meaning and transitive provenance rules remain those of [§13.6](language-spec/04-captures-and-access.md#136-canonical-interfaces-and-conservative-mutation).

Generated semantic clauses are interface/diagnostic notation. They belong to the `interface_file` entry point of the [formal grammar](formal-grammar.md), not to the ordinary Eldude source grammar. A generated interface is therefore not promised to be a copy-pastable source stub unless those interface-only clauses are omitted. Tools MUST label/render canonical interface output distinctly enough that interface-only syntax is not presented as ordinary author-written source.

These clauses do not create new user-denotable values, lifetime inequalities, capabilities, or author-written requirements.

## Generated native contracts

Every client-relevant audited native fact required by [§74.4](language-spec/12-interfaces-and-tooling.md#744-canonical-native-binding-metadata) MUST appear in a generated `ffi-contract { ... }` inside the declaration's `semantic { ... }` block. Ordinary types, effects, captures, and `Cleanup` remain part of the interface; the FFI clauses record the additional audited obligations and guarantees. These clauses are interface-only notation, never author-written source annotations. Mechanically derived symbol/calling-convention/layout facts remain in the separate ABI representation of [§74.2](language-spec/12-interfaces-and-tooling.md#742-public-abi).

A contract describes its attached declaration. `parameter(n) { ... }` selects zero-based callable parameter position, counting a receiver when present; `result { ... }` selects its result. `member(path) { ... }` selects a member by canonical identity, including a function in an `extern` block, a method/field, or an enum constructor/record-payload field of an exported nominal declaration. `component(n) { ... }` selects a zero-based stored tuple or positional constructor-payload component; selecting an enum constructor with `member` first distinguishes its payload from other variants. These selectors may nest to locate contracts on callback arguments/results or aggregate members. Within a selected subject, `pointer`, `output`, `callback`, and `marshalling` blocks distinguish the following applicable facts. Source parameter names are display labels, not contract identities.

The following vocabulary is normative. Values in the table are bare generated words, except capture bounds and `protocol(path)` references. `not_applicable` is permitted only when the fact genuinely does not apply; it is not an unknown guarantee. Unknown/unproved facts MUST be rendered as `unverified` where admitted or as an explicit unsafe precondition described by a protocol, rather than omitted to suggest safety.

| Subject | Keys, in canonical order | Values/meaning |
|---|---|---|
| Callable/native operation | `invocation` | `synchronous`, `offloaded`, `posted` |
| Callable/native operation | `blocking` | `none`, `may_block` |
| Callable/native operation | `finite-return` | `guaranteed`, `unverified`; the latter contributes `diverge` under [§55](language-spec/10-host-and-ffi.md#55-foreign-calls-blocking-and-suspension) |
| Callable/native operation | `native-cancellation` | `unsupported`, `request_only`, `completion_confirming`, or `protocol(path)` |
| Callable/native operation | `foreign-unwind` | `no_unwind`, `contained`, or `protocol(path)`; `contained` means caught by the shim without unwinding across live Eldude frames |
| Pointer | `ownership` | `borrowed`, `transferred_to_native`, `transferred_to_eldude`, or `protocol(path)` |
| Pointer | `retention` | `call_scoped`, `retained`, or `protocol(path)` |
| Pointer | `mutability` | `read_only`, `write_only`, `read_write` |
| Pointer | `aliasing` | `exclusive`, `shared_read`, `may_alias`, or `protocol(path)`; these do not remove ordinary access-conflict rules |
| Pointer or marshalling | `stable-address` | `required`, `not_required`; the implementation must establish any required stability |
| Pointer or marshalling | `provenance` | a normalized capture bound, `fresh_scoped`, or `protocol(path)` |
| Output | `initialization` | `always`, `on_success`, or `protocol(path)` |
| Output | `failure-state` | `initialized`, `uninitialized`, or `protocol(path)` |
| Callback or marshalling | `lifetime` | callback: `call_scoped`, `registration`, `root`, or `protocol(path)`; temporary marshalling: `callback_scoped` |
| Callback | `cardinality` | `may_skip` (zero or one), `exactly_once` (one), `may_repeat` (zero or more), or `protocol(path)` for other minimum/maximum or conditional bounds; measured over the complete lifecycle ([§56.2.1](language-spec/10-host-and-ffi.md#5621-lifecycle-cardinality-and-undelivered-obligations)) |
| Callback | `reentrancy` | `forbidden`, `permitted`, or `protocol(path)`; permission is per registration |
| Callback | `thread-affinity` | `same_domain_thread`, `posted_to_domain`, `audited_attached_thread`, or `protocol(path)` |
| Callback | `delivery-domain` | `current_domain`, `registration_domain`, or `protocol(path)` |
| Callback | `barrier` | `ordinary`, `stack_preserving`, `not_applicable`; `stack_preserving` requires the complete audited [§56.1](language-spec/10-host-and-ffi.md#561-same-domain-synchronous-callback) protocol |
| Callback | `suspension` | `forbidden`, `permitted`; permission does not authorize crossing an ordinary barrier |
| Callback | `algebraic-crossing` | `forbidden` |
| Callback | `cancellation` | `deferred`, `ordinary_points`, or `protocol(path)` |
| Callback | `defect` | `rendezvous` or `protocol(path)` describing the applicable Eldude-boundary/private-ABI protocol |
| Callback | `pending-defect-entry` | `suppressed` for synchronous entry; `not_applicable` for independently posted delivery |
| Callback | `deregistration`, `drain` | each `not_applicable` or `protocol(path)` specifying the prevention-of-acceptance and accepted/in-flight terminal obligations |
| Callback | `undelivered` | `discard`, `return_obligation`, `structural_discharge`, `not_applicable`, or `protocol(path)` covering the possible lifecycle outcomes of [§56.2.1](language-spec/10-host-and-ffi.md#5621-lifecycle-cardinality-and-undelivered-obligations) |
| Callback or lifetime owner | `shutdown` | `not_applicable` or `protocol(path)` |
| Any subject | `preconditions` | `protocol(path)` for additional audited validity, representation, encoding, lifetime, thread, or unsafe obligations |

Every applicable key MUST be emitted, including conservative ordinary-barrier facts. In addition to the listed scalar values, every key except the fixed `algebraic-crossing = forbidden` permits `protocol(path)` to describe compound/conditional behavior. The protocol MUST enumerate the alternatives and their guards/selection conditions; each alternative obeys the unconditional safe-language laws of [§§53](language-spec/10-host-and-ffi.md#53-foreign-storage-and-identity)–[56](language-spec/10-host-and-ffi.md#56-callbacks-and-execution-domains). This covers a callable that invokes inline on one path and posts/offloads on another, including the corresponding barrier, suspension, and pending-entry modes. It must not choose one scalar outcome that hides another. A protocol may supplement a fixed enum via `preconditions`; it cannot contradict that enum or relax a mandatory safe-language rule. Invalid scopes, repeated keys/selectors, invalid values, mismatches with the ordinary signature/effect row, or insufficient audited safety guarantees are interface errors.

Fixed callback facts have one source: the normalized callback-entry profile. For an ordinary synchronous entry, derive `barrier=ordinary`, `suspension=forbidden`, `cancellation=deferred`, and `pending-defect-entry=suppressed`. An audited stack-preserving synchronous entry derives the corresponding permitted-suspension/ordinary-cancellation profile and still suppresses entry after a pending defect. Independently posted delivery has no waiting foreign barrier or synchronous pending-entry state and executes with ordinary cancellation points. Every profile derives `algebraic-crossing=forbidden` in this version. Conditional protocols normalize each alternative separately. The renderer emits these derived facts for review, but metadata producers do not independently assert or override them. Canonical hashing uses the normalized profile and its deterministic expansion. Cardinality, reentrancy, lifetime, pointer stability, rendezvous details, and drain/discharge protocols remain independent audited facts.

A protocol reference names a stable canonical contract identity. The same semantic block MUST include exactly one `ffi-protocol path = "description";` for every referenced protocol, and descriptions must be self-contained with respect to their audited protocol behavior. Descriptions normalize line endings to LF; their remaining text is contract content, not subject to a prose-equivalence solver. The normalized description is part of the audited semantic contract and machine metadata, and MUST render all remaining client-relevant facts faithfully in human-readable terms; an opaque identifier/hash alone is insufficient. For a stack-preserving protocol this includes all [§56.1](language-spec/10-host-and-ffi.md#561-same-domain-synchronous-callback) obligations, and for a retained registration it includes the terminal drain/discharge outcomes of [§56.2.1](language-spec/10-host-and-ffi.md#5621-lifecycle-cardinality-and-undelivered-obligations). Tools may display the escaped string as prose, but must preserve its content in canonical serialization and semantic diffs. A changed guarantee, obligation, or protocol description invalidates semantic dependents independently of ABI changes.

Canonical rendering emits properties in the table's key order (a shared key appears once at its applicable subject), then subject blocks in the order `parameter`, `result`, `member`, `component`, `pointer`, `output`, `callback`, `marshalling`. Parameter/component selectors sort by numeric index, member selectors by canonical identity, recursively. Protocol descriptions follow the contract, sorted by canonical identity. Capture bounds use [§77](language-spec/12-interfaces-and-tooling.md#77-formatting-and-source-stability)'s ordering. The same normalized metadata MUST produce the same keys, selector identities, protocol identities/descriptions, and order independently of source labels or input metadata order.

For example, this is generated interface output, not source:

```text
module native;
pub fn call(callback: fn() -> Unit) -> Unit;
semantic {
    ffi-contract {
        invocation = synchronous;
        blocking = none;
        finite-return = guaranteed;
        native-cancellation = unsupported;
        foreign-unwind = no_unwind;
        parameter(0) {
            callback {
                lifetime = call_scoped;
                cardinality = exactly_once;
                reentrancy = forbidden;
                thread-affinity = same_domain_thread;
                delivery-domain = current_domain;
                barrier = ordinary;
                suspension = forbidden;
                algebraic-crossing = forbidden;
                cancellation = deferred;
                defect = protocol(native::CallRendezvous);
                pending-defect-entry = suppressed;
                deregistration = not_applicable;
                drain = not_applicable;
                undelivered = not_applicable;
                shutdown = not_applicable;
            }
        }
    }
    ffi-protocol native::CallRendezvous = "The shim returns a private native failure status on a defect or suppressed entry. Native code then returns to the waiting Eldude boundary. No pending invocation resumes normal Eldude work.";
}
```

The `exactly_once` clause describes normally completed lifecycles; defects still follow [§§20](language-spec/05-effects-and-failure.md#20-defects-and-assertions) and [56](language-spec/10-host-and-ffi.md#56-callbacks-and-execution-domains). The protocol description supplies the audited control path behind the `defect` clause, not a recoverable application result.

## Canonical interface ordering

A deterministic formatter is part of the standard toolchain.

Formatting is not parsing semantics. The parser must accept valid brace/semicolon syntax independent of indentation.

Compiler-generated public signatures MUST use the same canonical surface conventions as the formatter, including one final `| e` tail for an open effect row and ordinary `where e: NonAbandoning` spelling for the intrinsic effect-row constraint. They MUST also include the human-readable generated semantic clauses required by [§72.7](language-spec/12-interfaces-and-tooling.md#727-human-readable-semantic-interface-rendering) whenever a client-validity fact such as result provenance or mutable-owner status is not otherwise visible in the ordinary signature.

Generated canonical interfaces MUST render semantically unordered collections in one deterministic textual order:

- applied algebraic effect families sort by canonical fully qualified identity and then recursively canonicalized generic arguments; nominal error alternatives sort by canonical identity;
- `state<@r>` entries sort by canonical region-binder identity/order rather than incidental source spelling;
- duplicate effect labels are preserved, with same-family instance evidence in lexical nearest-to-outer order; any open row has exactly one tail, rendered after `|` following all fixed entries;
- intrinsic effect entries follow named/state entries in the fixed order `suspend`, then `diverge`;
- generated capture/provenance unions sort whole sources by canonical source slot (callable environment, then arguments by position); source names are replaced by positional parameter sources and duplicate entries are removed. Explicit provenance atoms follow by category and canonical binder/identity order, then capture-row variables by binder order;
- unordered constraint collections sort first by constrained binder order and then by canonical predicate identity;
- generated finite-positive parameter index sets sort in ascending parameter-position order.

Within a semantic subject, render representation and usage facts first, then result captures, mutable-owner region, finite-positive parameters, finite iteration, FFI facts, and nested selectors in [§72.9](language-spec/12-interfaces-and-tooling.md#729-generated-ffi-semantic-contracts)'s order. A usage block renders `Dup` before `Discard`; sort atoms in each conjunction by the ordinary canonical constraint order, deduplicate them, then sort/deduplicate conjunctions lexicographically and remove any conjunction strictly containing another. An empty conjunction is `true`; no offered conjunction is `false`. These are fixed syntactic normalization rules, not arbitrary logical/prose equivalence solving.

User-authored source need not be reordered solely to match this interface order; the requirement is for generated canonical renderings, stable hashing inputs, and deterministic generated documentation.

## JSON representation

`eldude-grammar.json` uses format `eldude-grammar`; `format_version` identifies the JSON schema version. `entry_points` names the ordinary source and generated interface starts. `lexical.tokens` and `lexical.skip` are ordered arrays of `{ "name": ..., "pattern": ... }`; array order retains lexical priority. `reserved_words` and `contextual_words` expose the word categories. `literal_vocabulary` lists the reachable literals for each entry point. String/character token recognition additionally validates the Unicode scalar range and excluded surrogate interval recorded in `lexical`.

`productions` maps each nonterminal to an array of alternatives. Each alternative is an ordered array of symbols; `[]` means epsilon. A symbol has exactly one key: `rule` references a nonterminal, `token` references a lexical category, and `literal` matches exact spelling. Names beginning with `@` are generated repetition helpers, not Eldude source tokens. This representation expands EBNF options and repetitions into ordinary BNF. `parsing_conventions` preserves the normative derivation/association rules above; consumers must apply them when building syntax trees.

## Regeneration and verification

From the repository root:

```sh
uv run python -m eldude.check_grammar --write
uv run python -m eldude.check_grammar
uv run python -m unittest discover -s tests -p 'test_grammar*.py'
```

The first command regenerates this document and the JSON export; the specification chapters are inputs and are not rewritten. The second rejects undefined symbols, duplicate productions, malformed EBNF, reserved-word drift, or stale generated publications. Tests cover accepted/rejected syntax, source/interface separation, JSON consumption, and stale-publication detection. Edit the EBNF or originating specification clauses, then regenerate; do not edit generated presentations directly.
