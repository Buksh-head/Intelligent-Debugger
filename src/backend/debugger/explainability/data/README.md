# Misconception training set

Training data for the misconception classifier (#66), which SHAP, LIME and DiCE
explain in #67. Created for #71.

## Provenance

**This is synthetic data written by the team. It is not student data.**

No labelled student submissions exist, and collecting them would require ethics
clearance the project does not have. Every snippet here was invented to resemble
a mistake a first-year Python student might plausibly make.

That has a direct consequence for any claim made about the classifier: it learns
what the team *believes* beginners get wrong, not what they observably get
wrong. Accuracy measured on this set says how well the model reproduces our
assumptions. It is not evidence about real students, and should never be
reported as though it were.

## Format

One JSON object per line (JSONL, so diffs stay readable in review).

| Field | Type | Meaning |
|---|---|---|
| `code` | string | The full submitted snippet |
| `error_type` | string | Python exception name, or `TimeoutError` for a sandbox timeout |
| `message` | string | The interpreter message a student would see |
| `timed_out` | bool | Whether the sandbox killed it rather than it raising |
| `misconception_label` | string | The target class, one of the 24 below |
| `ambiguous` | bool | Whether `error_type` alone is insufficient to pick the label |

## Taxonomy

Class names are deliberately written for students, not for us. A student who is
told "off-by-one" learns something; one told "iteration-boundary" does not. The
rule applied throughout: **a class earns its place only if it names a mistake a
hint can act on.**

### How the code is written

| Label | Covers |
|---|---|
| `missing-colon` | Forgot the `:` after `if`, `for`, `while`, `def`, `class` |
| `unclosed-bracket` | A `(`, `[`, `{` or quote never closed |
| `indentation` | Wrong or missing indentation, including mixed tabs and spaces |
| `assignment-vs-comparison` | Used `=` where `==` was meant |
| `invalid-syntax-other` | Reserved words as names, `return` outside a function, stray commas |

### Loops and repetition

| Label | Covers |
|---|---|
| `off-by-one` | Ran one step too far, usually `range`/`len` confusion |
| `empty-collection` | Indexing or popping something with nothing in it |
| `infinite-loop` | A loop whose condition never becomes false |
| `runaway-recursion` | A function that calls itself with no reachable base case |
| `collection-mutation` | Changing a list, dict or set while looping over it |

### Names and values

| Label | Covers |
|---|---|
| `name-typo` | Misspelled a name: `prnt`, `Ture`, `rang` |
| `use-before-assignment` | Used a name before it was given a value |
| `variable-scope` | Assigned to a global inside a function, or used a function's local outside it |
| `none-value` | Used the result of something that returns `None`, e.g. `nums = nums.sort()` |

### Types and data

| Label | Covers |
|---|---|
| `text-number-mix` | Mixed text and numbers, almost always unconverted `input()` |
| `conversion-failure` | `int()` or `float()` on text that is not a number |
| `wrong-container-operation` | An operation the type does not support: not iterable, not subscriptable, unhashable, immutable |
| `attribute-misuse` | Called a method the type does not have, e.g. `nums.push(3)` |
| `missing-member` | Assumed a key or value was present when it was not |
| `unpacking-mismatch` | Unpacked the wrong number of values |
| `argument-count` | Called a function with too few or too many arguments |
| `division-by-zero` | Divided or took a modulo by zero |

### Not a misconception

| Label | Covers |
|---|---|
| `slow-but-correct` | Terminating code that exceeded the sandbox limit. The logic is right |
| `environment` | Missing module or missing file. A setup problem, not a thinking problem |

These last two are deliberately separated. Labelling `fib(45)` as any kind of
mistake would be wrong, and telling a student their correct code contains a
misconception is worse than saying nothing. See the open question below about
whether they belong in the classifier at all.

## Current contents

266 rows across 24 classes and 16 distinct exception types. Every class has at
least 10 rows.

| Label | Rows | amb | | Label | Rows | amb |
|---|---|---|---|---|---|---|
| `off-by-one` | 16 | 2 | | `indentation` | 10 | 0 |
| `collection-mutation` | 15 | 8 | | `runaway-recursion` | 10 | 0 |
| `infinite-loop` | 14 | 0 | | `name-typo` | 10 | 0 |
| `division-by-zero` | 14 | 0 | | `use-before-assignment` | 10 | 0 |
| `missing-member` | 12 | 0 | | `variable-scope` | 10 | 0 |
| `attribute-misuse` | 12 | 0 | | `text-number-mix` | 10 | 0 |
| `conversion-failure` | 12 | 0 | | `none-value` | 10 | 0 |
| `wrong-container-operation` | 11 | 0 | | `environment` | 10 | 0 |
| `missing-colon` | 10 | 0 | | `unpacking-mismatch` | 10 | 0 |
| `unclosed-bracket` | 10 | 0 | | `slow-but-correct` | 10 | 10 |
| `assignment-vs-comparison` | 10 | 0 | | `empty-collection` | 10 | 0 |
| `invalid-syntax-other` | 10 | 0 | | `argument-count` | 10 | 0 |

## The ambiguous subset

20 rows are flagged `ambiguous`: the rows where `error_type` alone cannot
determine the label. Three shapes:

- **`IndexError` from mutation, not from a bad bound.** `for i in
  range(len(nums)): nums.pop()` raises exactly the same `IndexError` as a plain
  off-by-one, but the misconception differs and so does the useful hint.
- **A timeout that is not an infinite loop.** `fib(45)` and a 100-million
  iteration accumulator both time out while terminating correctly.
- **A timeout from growing a list while looping over it**, which is a mutation
  problem wearing a timeout's clothes.

**Evaluation must report accuracy on this subset separately.** Headline accuracy
across all 266 rows will look strong for a reason that flatters the model: for
the other 246 rows the exception type and message very nearly determine the
label, so a lookup table would score just as well. The ambiguous number is the
only one that says whether the classifier earns its place.

## Known bias and limitations

1. **The fine-grained taxonomy weakens the ML case.** This is the important one.
   Splitting into 24 classes makes labels genuinely more useful to students, but
   nearly every new class is perfectly determined by the error message text. The
   model increasingly just reads `message`, so SHAP will attribute almost
   everything to TF-IDF tokens, and the structural AST features will barely
   register. Better product, weaker evidence that a classifier beats a lookup
   table. Both are true; the trade-off was made deliberately.
2. **Only 3 of 24 classes appear in the ambiguous subset.** The other 21 are
   entirely unambiguous, so they contribute nothing to the figure that actually
   matters.
3. **Roughly 11 rows per class is thin** for a 24-way multi-class model with
   TF-IDF features. Expect unstable per-class performance and a wide confidence
   interval on any accuracy number.
4. **Author bias.** Written by one contributor across two sittings. Snippets
   cluster around a narrow idea of beginner code and reuse variable names
   (`nums`, `total`, `count`), which the text features may latch onto as signal.
5. **Clean, short snippets.** Most rows are three to six lines. Real submissions
   are longer, messier, and often contain several problems at once, so
   `total_lines` and `line_number_ratio` will see a much narrower range here
   than in production.
6. **Idealised error messages.** Written from memory of CPython 3.12 output.
   Wording differs across versions, and the classifier reads this text directly.
7. **Class balance is artificial.** Ten to sixteen rows each is not how these
   errors are distributed in a real cohort. Syntax errors in particular are far
   more common in week 1 than everything else combined.

## Open questions for the team

- **Should `slow-but-correct` and `environment` be classes at all?** Neither is
  a misconception. A student whose code is correct but slow has nothing to fix
  conceptually, and a missing module is a setup problem. Forcing them through a
  misconception classifier means the hint layer must special-case them anyway.
  The alternative is a separate non-misconception outcome upstream of the model.
  This is a design-record change, not a data change.
- **Is 24 classes too many to be defensible?** See limitation 1. If the
  evaluation in #73 shows the ambiguous-subset accuracy is no better than a
  lookup table, the honest conclusion is that the classifier is decorative and
  the taxonomy would be better implemented as rules, with the XAI story revised
  accordingly. Worth deciding *before* results arrive rather than after.

## Outstanding

- [ ] **Tutor review.** #71's Definition of Done requires review by a teammate
      with first-year tutoring experience. The labels here are a first pass and
      have **not** been reviewed. The 24-class split in particular needs a
      sanity check: several boundaries (`wrong-container-operation` vs
      `attribute-misuse`, `use-before-assignment` vs `variable-scope`) are
      judgement calls that a tutor may draw differently.
