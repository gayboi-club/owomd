# [owomd](https://github.com/gayboi-club/owomd)

A custom markdown format for gays, by [gays](https://gayboi.club/) :3c

---

## Architecture

Rust project compiling to a simple cross-platform binary.

### Processing steps

- Metadata Header processing — Metadata header is to be parsed (if existing), stored in state as metadata for whatever plugins use it (i.e final render pass), and cut out the raw text from being parsed in later stages (i.e a blacklist "Do not process" span)
- Tokenization
  - Escape sequences
  - Ranged tokens
    - Block quotes
    - Code blocks
    - Iterator syntax
  - Inline tokens
    - Placeholders
    - Links
    - etc…
- Rendering of the HTML skeleton
  - Placeholder evaluation on the fly (Note: Doing placeholder evaluation in this stage makes it so that if a placeholder contains a literal string `\*\*test\*\*`, it will not be bolded. This is intentional)
- Final render pass — Styles, `<head>`, etc..

### Input/Output

Processor should be spawned with one required argument and one optional argument, the required argument should be a path to a template file.

Example:

```
./owomd /path/to/template.md.owo
./owomd /path/to/template.md.owo --force-stdin-read
```

Processor can take in placeholder information as json, see [Placeholder rules](#placeholder-rules). If stdin is a terminal and `--force-stdin-read` is not set, pretend `{}` was piped in. If invalid (syntactically or semantically) json is piped in, error.

---

## Metadata Header

A metadata header can optionally exist on a document, the header contains yaml metadata about the document.

If a document contains a header, it must start with `$HEADER_BEGIN` and contain `$HEADER_END`. If `$HEADER_BEGIN` is present while `$HEADER_END` is not, this is a semantic error.

If a document contains multiple `$HEADER_END` instances, the first one is treated as special and all other instances are treated as literal text.

If a document contains `$HEADER_END` while `$HEADER_BEGIN` is not present, `$HEADER_END` is treated as literal text.

Example:

```
$HEADER_BEGIN
title: Meowing test :3c
$HEADER_END

- So yeah, this text, $HEADER_END, is treated as literal
```

Examples of edge cases:

Malformed header, is not valid yaml (Error):

```
$HEADER_BEGIN
lmao
$HEADER_END
```

No header beginning (do not implicitly create a header, treat everything as normal):

```
title: Edge case example
$HEADER_END
```

### Supported metadata fields

| Field | Type | Description |
|-------|------|-------------|
| `title` | String | Page title, used for `<title>` and `og:title` |
| `description` | String | Page description, used for `<meta name="description">` and `og:description` |
| `image` | String | Open Graph image URL, used for `og:image` and `twitter:card` |
| `url` | String | Canonical URL, used for `og:url` |
| `site_name` | String | Site name, used for `og:site_name` |
| `align` | String | Page alignment: `center` (default), `left`, or `right` |
| `gradient_colors` | List of Strings | Colors for `==text==` gradient spans, e.g. `["#f472b6", "#8b5cf6"]` |
| `css_imports` | List of Strings | Remote stylesheets to import |
| `custom_css` | String | Inline CSS to inject |

Example with all fields:

```
$HEADER_BEGIN
title: My Awesome Page
description: A cool site about things
image: https://example.com/og.png
url: https://example.com
site_name: My Site
align: center
gradient_colors: ["#f472b6", "#8b5cf6", "#06b6d4"]
css_imports:
  - "https://fonts.googleapis.com/css2?family=Outfit:wght@400;700&display=swap"
custom_css: |
  body { font-family: 'Outfit', sans-serif; }
$HEADER_END
```

---

## The format

### Escapes

| Syntax | Description |
|--------|-------------|
| `\unnnn` | All 4 "n" characters must be valid hex → Arbitrary UTF-8 code point |
| `\u{n+}` | All "n" characters must be valid hex, n+ meaning 1 or more "n" characters → Arbitrary content and length UTF-8 characters. Values above U+10FFFF should be treated as errors. |
| `\xnn` | Both "n" characters must be valid hex → Shorthand for `\u00xx` |

> [!NOTE]
> If a nullbyte appears while parsing or as a result of an escape character, this is an error, a processor should immediately complain and exit.

> [!NOTE]
> If an explicitly defined escape pattern (like `\xnn`) is invoked, parse it properly or error, a parser must not fall back on pretending `x` is an escaped character and `nn` is literal text following it.

As a catch all default, for character `\x`, if `x` has semantic meaning, no it doesn't. It is optional for the parser to maintain a list of "valid" escapes and warn the user if an invalid escape is used (i.e `\l`). The exception to this is in the case of `\\`, in which case the next character is NOT escaped (the backslash itself is the escaped character).

> [!NOTE]
> If a character is escaped where normally it would not have semantic meaning (like for example the line `Text here \> stuff`), still treat it as a normal escape.

Examples (where placeholder input is `{"stuff": "meow"}`):

| Input | Output |
|-------|--------|
| `\u2122` | ™ |
| `\u{1f431}` | 🐱 |
| `\xe4` | ä |
| `\${stuff}` | `${stuff}` |
| `\\${stuff}` | `\meow` |

### Header lines

```
# - h1
## - h2
```

Etc. until h6. For reference, header lines should get matched by this expression:

```
^\#{1,6}\s+\S.*$
```

Header hierarchy is strict. This is **invalid**:

```
# h1
### h3
```

This is **valid**:

```
# h1
## h2
### h3
```

This rule is in place to aid ToC generation and for easier browsing.

As for whitespace after the `#+`:

```
##Test
```

This is an invalid header, but it should be treated as literally `##Test`.

### Emphasis

| Syntax | Result |
|--------|--------|
| `*italics*` | *italics* |
| `**bold**` | **bold** |
| `_underline_` | underline |
| `==gradient==` | gradient text (requires `gradient_colors` in header) |
| `` `inline codeblock` `` | `inline codeblock` |

> [!NOTE]
> If there's a dangling `*`, a parser should warn about this, recommend the user to escape it, and treat it as a literal. Emphasis automatically terminates per line.

For example, this gets rendered literally:

```
*stuff
*
```

### Gradient text

Requires `gradient_colors` to be defined in the [Metadata Header](#metadata-header). Any text wrapped in `==` will be rendered with a gradient.

```
This is ==gradient text== right here!
```

### Page alignment

Page alignment is controlled via the `align` field in the [Metadata Header](#metadata-header). Acceptable values are `center` (default), `left`, and `right`.

### Code blocks

Codeblocks are defined with ` ``` ` syntax. (Reminder: to escape a codeblock properly, prepend each individual grave with a backslash.)

Example:

````
```rs
fn main() -> i32 {
  println!("meow mrrow");
}
```
````

> [!NOTE]
> The language identifier and codeblock contents must be on separate lines, and the language identifier must be on the same line as the initial 3 graves (the ending 3 graves can be either inline or on their own line).

Code blocks can also have a templating mode:

````
```rs+templating
fn main() -> i32 \{
  println!("${stuff}");
\}
```
````

> [!NOTE]
> Because `{` carries semantic meaning in general, it should be escaped in templating codeblocks. For this reason it is recommended to use templating code blocks sparingly.

The templating tag (`+templating`) does not have to accompany a language identifier; `+templating` is perfectly valid.

Escaping, placeholder and iterator rules apply in these code blocks.

### Links

See markdown standard, i.e:

```
[Meow owo](https://amcalledglitchy.dev)
```

→ [Meow owo](https://amcalledglitchy.dev)

To convert text to a link, use angle brackets as per standard.

### Images

As per md standard, use the `![text](link)` format for images.

### Lists

See markdown standard for lists, i.e:

```
- stuff
- stuff2
```

Gets turned into:

- stuff
- stuff2

Same for numbered lists:

```
1. haii
2. owo
```

Gets turned into:

1. haii
2. owo

### Quotes

Rules for quotes:

- Each line must start with `>`, quotes get "broken" if there is a line without a quote
- A line just containing `>` is a valid quote
- Quotes can be nested, i.e `> >` or `>>`
- Quotes do not affect styling, i.e creating a header inside a quote block like `> # meow` is perfectly valid

### Placeholders

Where placeholder input is `{"stuff": "meow :3"}`, this:

```
${stuff}
```

Will render as `meow :3`.

Should be noted that only strings can be used in a placeholder, other types should error.

You can also do field access of a map from a placeholder. Where placeholder input is `{"stuff": {"nested": "haii"}}`, this:

```
${stuff.nested}
```

Will render as `haii`.

---

If a field does not exist — where placeholder input is `{}`, this:

```
${nonexistent}
```

Should give an error like:

```
! Evaluation error (line 1): Key "nonexistent" does not exist.
```

And on invalid type for traversal — where placeholder input is `{"stuff": "woof"}`, this:

```
${stuff.field}
```

Should give an error like:

```
! Evaluation error (line 1): Path "stuff.field" is invalid, "stuff" exists but is of type String
```

Array contents also cannot be accessed like this.

### Iterators

Where placeholder input is `{"stuff": [ "item 1", "item 2" ]}`, this:

```
$iterate stuff as item{
- ${item}
}
```

Will render as:

```
- item 1
- item 2
```

Should also be noted that:

- Iterators can nest, i.e this is valid:

```
$iterate list1 as level1{
$iterate list2 as level2{
- 1: ${level1}, 2: ${level2}
}
}
```

- Iterators cannot iterate over maps (planned for the future, currently we're keeping it simple), nor strings.
- The iterator "signature" line (the `$iterate stuff as item{` part) should remain in one line.

Nested iterators cannot override existing variables (including higher iterators) to prevent shadowing bugs. This:

```
$iterate list1 as i{
$iterate list2 as i{
- ${i}
}
}
```

Should give an error like:

```
! Evaluation error (line 2): Iteration over list2 as "i" would override existing variable sharing the same name.
```

---

## Placeholder rules

Placeholders are supplied to the renderer via json input.

**Allowed types:** Map, Array, String

All other types should be cast to a string or whatever is relevant by the application layer, NOT the parser — parser should reject other types.

The top level of the placeholder must be a map.

An array cannot contain mixed types. All types must match, along with map structure. For example:

```json
{"array": [
  {"a": "meow", "c": "chirp"},
  {"b": "woof", "c": "oink"}
]}
```

Is invalid due to `array[1]` containing `"b"` while `array[0]` does not. In the future there are plans to create conditional logic and optionals.
