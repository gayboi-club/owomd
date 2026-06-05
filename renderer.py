import html

from ast_parser import parse_inline, TextNode, EmphasisNode, LinkNode, ImageNode, PlaceholderNode, OwomdError
from block_parser import parse_blocks

def resolve_path(context, path, line_num):
    parts = path.split('.')
    curr = context
    curr_path = []
    for part in parts:
        curr_path.append(part)
        if not isinstance(curr, dict):
            raise OwomdError(f"Evaluation error (line {line_num}): Path \"{'.'.join(curr_path)}\" is invalid, \"{curr_path[-2]}\" exists but is of type {type(curr).__name__}")
        if part not in curr:
            raise OwomdError(f"Evaluation error (line {line_num}): Key \"{part}\" does not exist.")
        curr = curr[part]
    if not isinstance(curr, str):
        raise OwomdError(f"Evaluation error (line {line_num}): Path \"{path}\" evaluates to a non-string.")
    return curr

def resolve_iterable(context, path, line_num):
    parts = path.split('.')
    curr = context
    curr_path = []
    for part in parts:
        curr_path.append(part)
        if not isinstance(curr, dict):
            raise OwomdError(f"Evaluation error (line {line_num}): Path \"{'.'.join(curr_path)}\" is invalid")
        if part not in curr:
            raise OwomdError(f"Evaluation error (line {line_num}): Key \"{part}\" does not exist.")
        curr = curr[part]
    if not isinstance(curr, list):
        raise OwomdError(f"Evaluation error (line {line_num}): Path \"{path}\" evaluates to a non-list.")
    return curr

def render_inline(text, context, line_num):
    # Parse inline nodes and evaluate placeholders :3c
    nodes = parse_inline(text, line_num)
    res = ""
    for node in nodes:
        if isinstance(node, TextNode):
            res += html.escape(node.text)
        elif isinstance(node, PlaceholderNode):
            val = resolve_path(context, node.path, node.line_num)
            res += html.escape(val)
        # Process Emphasis, Links, Images here :3c
    return res

def render_blocks(blocks, context):
    out = ""
    for block in blocks:
        btype = block[0]
        if btype == 'header':
            _, level, text, line_num = block
            rendered = render_inline(text, context, line_num)
            out += f"<h{level}>{rendered}</h{level}>\n"
        elif btype == 'paragraph':
            _, text, line_num = block
            rendered = render_inline(text, context, line_num)
            out += f"<p>{rendered}</p>\n"
        elif btype == 'codeblock':
            _, lang, templating, lines = block
            # Evaluate placeholders if templating :3c
            code_out = ""
            for i, line in enumerate(lines):
                if templating:
                    pass
            out += f"<pre><code class=\"language-{lang}\">\n" + code_out + "</code></pre>\n"
            
        elif btype == 'quote':
            _, quote_blocks = block
            out += f"<blockquote>\n{render_blocks(quote_blocks, context)}</blockquote>\n"
        elif btype == 'ul':
            _, items = block
            out += "<ul>\n"
            for item in items:
                _, text, line_num = item
                out += f"<li>{render_inline(text, context, line_num)}</li>\n"
            out += "</ul>\n"
        elif btype == 'ol':
            _, items = block
            out += "<ol>\n"
            for item in items:
                _, text, line_num = item
                out += f"<li>{render_inline(text, context, line_num)}</li>\n"
            out += "</ol>\n"
        elif btype == 'iterator':
            _, path, var_name, iter_blocks, line_num = block
            iterable = resolve_iterable(context, path, line_num)
            if var_name in context:
                raise OwomdError(f"Evaluation error (line {line_num}): Iteration over {path} as \"{var_name}\" would override existing variable sharing the same name.")
            for item in iterable:
                new_context = context.copy()
                new_context[var_name] = item
                out += render_blocks(iter_blocks, new_context)
    return out

