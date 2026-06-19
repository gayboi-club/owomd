import sys
import json
import os
import re
import yaml
import html
import http.server
import socketserver
import urllib.parse

class OwomdError(Exception):
    pass

def extract_metadata(text):
    begin_marker = "$HEADER_BEGIN"
    end_marker = "$HEADER_END"
    
    # Multiple $HEADER_ENDs handled here :3
    if begin_marker in text:
        start_idx = text.find(begin_marker)
        end_idx = text.find(end_marker, start_idx + len(begin_marker))
        if end_idx == -1:
            raise OwomdError("Header started with $HEADER_BEGIN but no $HEADER_END found.")
        header_content = text[start_idx + len(begin_marker):end_idx].strip()
        try:
            metadata = yaml.safe_load(header_content)
        except yaml.YAMLError as e:
            raise OwomdError(f"Malformed header, is not valid yaml: {e}")
            
        remaining_text = text[:start_idx] + text[end_idx + len(end_marker):]
        if remaining_text.startswith('\n'):
            remaining_text = remaining_text[1:]
        return metadata, remaining_text
        
    return {}, text

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

# Tokenize blocks :3c
def parse_blocks(lines, start_line_num=1):
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        line_num = start_line_num + i

        # Alignment directive :3
        m = re.match(r'^\$align:\s*(center|left|right)$', line)
        if m:
            blocks.append(('align_directive', m.group(1)))
            i += 1
            continue

        # Iterator :3
        m = re.match(r'^\$iterate\s+([a-zA-Z0-9_\.]+)\s+as\s+([a-zA-Z0-9_]+)\s*\{$', line)
        if m:
            path, var_name = m.groups()
            depth = 1
            body = []
            j = i + 1
            while j < len(lines):
                if re.match(r'^\$iterate\s+([a-zA-Z0-9_\.]+)\s+as\s+([a-zA-Z0-9_]+)\s*\{$', lines[j]):
                    depth += 1
                elif lines[j].strip() == '}':
                    depth -= 1
                    if depth == 0:
                        break
                body.append(lines[j])
                j += 1
            
            blocks.append(('iterator', path, var_name, parse_blocks(body, start_line_num + i + 1), line_num))
            i = j + 1
            continue

        # Code block :3
        m = re.match(r'^```(.*)$', line)
        if m:
            lang_part = m.group(1).strip()
            templating = '+templating' in lang_part
            lang = lang_part.replace('+templating', '').strip()
            
            body = []
            j = i + 1
            while j < len(lines):
                if lines[j].strip().startswith('```'):
                    break
                body.append(lines[j])
                j += 1
                
            blocks.append(('codeblock', lang, templating, body, line_num))
            i = j + 1
            continue

        # Quote :3
        if line.startswith('>'):
            quote_lines = []
            j = i
            while j < len(lines) and lines[j].startswith('>'):
                ql = lines[j][1:]
                if ql.startswith(' '):
                    ql = ql[1:]
                quote_lines.append(ql)
                j += 1
                
            # Check for GitHub-style alerts
            if len(quote_lines) > 0:
                m = re.match(r'^\[\!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]$', quote_lines[0].strip(), re.IGNORECASE)
                if m:
                    alert_type = m.group(1).lower()
                    blocks.append(('alert', alert_type, parse_blocks(quote_lines[1:], start_line_num + i + 1)))
                    i = j
                    continue

            blocks.append(('quote', parse_blocks(quote_lines, start_line_num + i)))
            i = j
            continue

        # Header :3
        m = re.match(r'^(\#{1,6})\s+(\S.*)$', line)
        if m:
            blocks.append(('header', len(m.group(1)), m.group(2), line_num))
            i += 1
            continue

        # List (Unordered) :3
        if line.startswith('- '):
            blocks.append(('ul_item', line[2:], line_num))
            i += 1
            continue

        # List (Ordered) :3
        m = re.match(r'^\d+\.\s+(.*)$', line)
        if m:
            blocks.append(('ol_item', m.group(1), line_num))
            i += 1
            continue

        # Paragraph / empty :3
        if line.strip() == '':
            blocks.append(('empty',))
            i += 1
            continue

        blocks.append(('paragraph', line, line_num))
        i += 1

    # Group lists :3c
    grouped = []
    curr_list = None
    list_type = None

    for b in blocks:
        btype = b[0]
        if btype == 'ul_item':
            if list_type != 'ul':
                if curr_list: grouped.append((list_type, curr_list))
                curr_list = []
                list_type = 'ul'
            curr_list.append(b)
        elif btype == 'ol_item':
            if list_type != 'ol':
                if curr_list: grouped.append((list_type, curr_list))
                curr_list = []
                list_type = 'ol'
            curr_list.append(b)
        elif btype == 'empty':
            if curr_list: grouped.append((list_type, curr_list))
            curr_list = None
            list_type = None
        else:
            if curr_list: grouped.append((list_type, curr_list))
            curr_list = None
            list_type = None
            grouped.append(b)

    if curr_list:
        grouped.append((list_type, curr_list))

    return grouped

def parse_inline(text, line_num=0):
    pattern = re.compile(
        r'(!\[.*?\]\(.*?\))|'
        r'(\[.*?\]\(.*?\))|'
        r'(<https?://[^>]+>)|'
        r'(<\/?[a-zA-Z][^>]*>)|'
        r'(\*\*.*?\*\*)|'
        r'(\*.*?\*)|'
        r'(_.*?_)|'
        r'(==.*?==)|'
        r'(`.*?`)'
    )
    
    nodes = []
    idx = 0
    while idx < len(text):
        # Handle escape sequences :3
        if text[idx] == '\\' and idx + 1 < len(text):
            nxt = text[idx+1]
            if nxt == 'u':
                if idx + 2 < len(text) and text[idx+2] == '{':
                    end = text.find('}', idx + 3)
                    if end != -1:
                        hex_str = text[idx+3:end]
                        try:
                            val = int(hex_str, 16)
                            if val > 0x10FFFF:
                                raise OwomdError(f"Escape value too large: {hex_str}")
                            nodes.append(('text', chr(val)))
                            idx = end + 1
                            continue
                        except ValueError:
                            pass
                if idx + 5 < len(text):
                    hex_str = text[idx+2:idx+6]
                    try:
                        val = int(hex_str, 16)
                        nodes.append(('text', chr(val)))
                        idx += 6
                        continue
                    except ValueError:
                        pass
            elif nxt == 'x':
                if idx + 3 < len(text):
                    hex_str = text[idx+2:idx+4]
                    try:
                        val = int(hex_str, 16)
                        nodes.append(('text', chr(val)))
                        idx += 4
                        continue
                    except ValueError:
                        pass
            elif nxt == '$':
                nodes.append(('text', '$'))
                idx += 2
                continue
            nodes.append(('text', nxt))
            idx += 2
            continue

        # Try regex patterns anchored at current position :3c
        m = pattern.match(text, idx)
        if m:
            match_str = m.group(0)
            if match_str.startswith('![') and match_str.endswith(')'):
                alt = match_str[2:match_str.find(']')]
                url = match_str[match_str.find('(')+1:-1]
                nodes.append(('image', alt, url))
            elif match_str.startswith('[') and match_str.endswith(')'):
                alt = match_str[1:match_str.find(']')]
                url = match_str[match_str.find('(')+1:-1]
                nodes.append(('link', alt, url))
            elif match_str.startswith('<') and match_str[1:2] in 'hH':
                url = match_str[1:-1]
                nodes.append(('link', url, url))
            elif match_str.startswith('<'):
                nodes.append(('raw_html', match_str))
            elif match_str.startswith('**'):
                nodes.append(('bold', match_str[2:-2]))
            elif match_str.startswith('*'):
                nodes.append(('italic', match_str[1:-1]))
            elif match_str.startswith('_'):
                nodes.append(('underline', match_str[1:-1]))
            elif match_str.startswith('==') and match_str.endswith('=='):
                inner = match_str[2:-2]
                if ':' in inner:
                    gname, _, gtext = inner.partition(':')
                    if gname:
                        nodes.append(('gradient', gtext, gname))
                    else:
                        nodes.append(('gradient', inner))
                else:
                    nodes.append(('gradient', inner))
            elif match_str.startswith('`'):
                nodes.append(('code', match_str[1:-1]))
            idx = m.end()
            continue

        # Scan ahead for the next escape or pattern match :3
        next_idx = idx + 1
        while next_idx < len(text):
            if text[next_idx] == '\\':
                break
            if pattern.match(text, next_idx):
                break
            next_idx += 1
        nodes.append(('text', text[idx:next_idx]))
        idx = next_idx

    # Process placeholders in the text and raw_html nodes :3c
    final_nodes = []
    for node in nodes:
        if node[0] in ('text', 'raw_html'):
            t = node[1]
            while True:
                s = t.find('${')
                if s == -1: break
                e = t.find('}', s)
                if e == -1: break
                if s > 0:
                    final_nodes.append((node[0], t[:s]))
                final_nodes.append(('placeholder', t[s+2:e].strip(), line_num))
                t = t[e+1:]
            if t:
                final_nodes.append((node[0], t))
        else:
            final_nodes.append(node)

    return final_nodes

def render_inline(text, context, line_num):
    nodes = parse_inline(text, line_num)
    res = ""
    for node in nodes:
        t = node[0]
        if t == 'text':
            res += html.escape(node[1])
        elif t == 'placeholder':
            val = resolve_path(context, node[1], node[2])
            res += html.escape(val)
        elif t == 'bold':
            res += f"<strong>{render_inline(node[1], context, line_num)}</strong>"
        elif t == 'italic':
            res += f"<em>{render_inline(node[1], context, line_num)}</em>"
        elif t == 'underline':
            res += f"<u>{render_inline(node[1], context, line_num)}</u>"
        elif t == 'gradient':
            if len(node) > 2:
                cls = f'owomd-gradient-{html.escape(node[2])}'
            else:
                cls = 'owomd-gradient'
            res += f'<span class="{cls}">{render_inline(node[1], context, line_num)}</span>'
        elif t == 'code':
            res += f"<code>{html.escape(node[1])}</code>"
        elif t == 'link':
            res += f"<a href=\"{html.escape(render_inline(node[2], context, line_num))}\">{render_inline(node[1], context, line_num)}</a>"
        elif t == 'image':
            res += f"<img src=\"{html.escape(render_inline(node[2], context, line_num))}\" alt=\"{html.escape(render_inline(node[1], context, line_num))}\" />"
        elif t == 'raw_html':
            res += node[1]
    return res

def render_blocks(blocks, context, current_align='inherit'):
    out = ""
    for block in blocks:
        btype = block[0]
        if btype == 'align_directive':
            current_align = block[1]
            continue

        align_attr = f' class="text-align-{current_align}"' if current_align != 'inherit' else ''

        if btype == 'header':
            _, level, text, line_num = block
            rendered = render_inline(text, context, line_num)
            out += f"<h{level}{align_attr}>{rendered}</h{level}>\n"
        elif btype == 'paragraph':
            _, text, line_num = block
            rendered = render_inline(text, context, line_num)
            out += f"<p{align_attr}>{rendered}</p>\n"
        elif btype == 'codeblock':
            _, lang, templating, lines, line_num = block
            code_out = ""
            for line in lines:
                if templating:
                    # Parse only escapes and placeholders for templating :3
                    nodes = parse_inline_code(line, line_num)
                    for n in nodes:
                        if n[0] == 'text': code_out += html.escape(n[1])
                        elif n[0] == 'placeholder': 
                            val = resolve_path(context, n[1], n[2])
                            code_out += html.escape(val)
                    code_out += "\n"
                else:
                    # Normal codeblocks just print as is with HTML escaping :3c
                    code_out += html.escape(line) + "\n"
                    
            if lang:
                out += f"<pre{align_attr}><code class=\"language-{lang}\">\n{code_out}</code></pre>\n"
            else:
                out += f"<pre{align_attr}><code>\n{code_out}</code></pre>\n"
        elif btype == 'quote':
            _, quote_blocks = block
            out += f"<blockquote{align_attr}>\n{render_blocks(quote_blocks, context, current_align)}</blockquote>\n"
        elif btype == 'alert':
            _, alert_type, alert_blocks = block
            titles = {
                'note': 'Note',
                'tip': 'Tip',
                'important': 'Important',
                'warning': 'Warning',
                'caution': 'Caution'
            }
            title = titles.get(alert_type, 'Alert')
            alert_cls = f'owomd-alert owomd-alert-{alert_type}'
            if current_align != 'inherit':
                alert_cls += f' text-align-{current_align}'
            out += f'<div class="{alert_cls}">\n'
            out += f'  <div class="owomd-alert-title">{title}</div>\n'
            out += f'  <div class="owomd-alert-content">\n'
            out += render_blocks(alert_blocks, context, current_align)
            out += f'  </div>\n'
            out += f'</div>\n'
        elif btype == 'ul':
            _, items = block
            out += f"<ul{align_attr}>\n"
            for item in items:
                _, text, line_num = item
                out += f"<li>{render_inline(text, context, line_num)}</li>\n"
            out += "</ul>\n"
        elif btype == 'ol':
            _, items = block
            out += f"<ol{align_attr}>\n"
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
                out += render_blocks(iter_blocks, new_context, current_align)
    return out

def parse_inline_code(text, line_num):
    nodes = []
    i = 0
    current_text = ""
    def flush_text():
        nonlocal current_text
        if current_text:
            nodes.append(('text', current_text))
            current_text = ""
    while i < len(text):
        if text[i] == '\\':
            if i + 1 >= len(text):
                current_text += '\\'
                i += 1
                break
            nxt = text[i+1]
            if nxt == 'u':
                if i + 2 < len(text) and text[i+2] == '{':
                    end = text.find('}', i + 3)
                    if end != -1:
                        hex_str = text[i+3:end]
                        try:
                            val = int(hex_str, 16)
                            if val > 0x10FFFF: raise OwomdError(f"Escape value too large: {hex_str}")
                            current_text += chr(val)
                            i = end + 1
                            continue
                        except ValueError: pass
                if i + 5 < len(text):
                    hex_str = text[i+2:i+6]
                    try:
                        val = int(hex_str, 16)
                        current_text += chr(val)
                        i += 6
                        continue
                    except ValueError: pass
            elif nxt == 'x':
                if i + 3 < len(text):
                    hex_str = text[i+2:i+4]
                    try:
                        val = int(hex_str, 16)
                        current_text += chr(val)
                        i += 4
                        continue
                    except ValueError: pass
            current_text += nxt
            i += 2
            continue
        elif text.startswith('${', i):
            end = text.find('}', i + 2)
            if end != -1:
                flush_text()
                path = text[i+2:end].strip()
                nodes.append(('placeholder', path, line_num))
                i = end + 1
                continue
        current_text += text[i]
        i += 1
    flush_text()
    return nodes

def process_document(text, placeholder_data):
    if '\x00' in text:
        raise OwomdError("Null byte found in input.")
    
    metadata, content = extract_metadata(text)
    
    lines = content.split('\n')
    blocks = parse_blocks(lines)
    html_output = render_blocks(blocks, placeholder_data)
    
    title = metadata.get('title', '')
    description = metadata.get('description', '')
    image = metadata.get('image', '')
    site_url = metadata.get('url', '')
    site_name = metadata.get('site_name', '')
    align = metadata.get('align', 'center')
    gradient_colors = metadata.get('gradient_colors', [])
    gradients = metadata.get('gradients', {})

    css_imports = metadata.get('css_imports', [])
    if isinstance(css_imports, str):
        css_imports = [css_imports]

    custom_css = metadata.get('custom_css', '')

    # Build head tags :3c
    head_tags = ""
    if title:
        head_tags += f'    <title>{html.escape(title)}</title>\n'
        head_tags += f'    <meta property="og:title" content="{html.escape(title)}">\n'
    if description:
        head_tags += f'    <meta name="description" content="{html.escape(description)}">\n'
        head_tags += f'    <meta property="og:description" content="{html.escape(description)}">\n'
    if image:
        head_tags += f'    <meta property="og:image" content="{html.escape(image)}">\n'
        head_tags += '    <meta name="twitter:card" content="summary_large_image">\n'
    if site_url:
        head_tags += f'    <meta property="og:url" content="{html.escape(site_url)}">\n'
    if site_name:
        head_tags += f'    <meta property="og:site_name" content="{html.escape(site_name)}">\n'

    css_links_html = ""
    for imp in css_imports:
        css_links_html += f'    <link rel="stylesheet" href="{html.escape(imp)}">\n'

    custom_css_html = ""
    if custom_css:
        custom_css_html = f'    <style>\n{custom_css}\n    </style>\n'

    gradient_css = ""
    all_gradients = {}
    if gradient_colors:
        all_gradients['default'] = gradient_colors
    if gradients:
        all_gradients.update(gradients)

    if all_gradients:
        gradient_css = '    <style>\n'
        for name, colors_list in all_gradients.items():
            colors = ", ".join(colors_list)
            cls = 'owomd-gradient' if name == 'default' else f'owomd-gradient-{name}'
            gradient_css += (
                f'        .{cls} {{\n'
                f'            background: linear-gradient(135deg, {colors});\n'
                f'            -webkit-background-clip: text;\n'
                f'            background-clip: text;\n'
                f'            color: transparent;\n'
                f'            display: inline;\n'
                f'        }}\n'
            )
        gradient_css += '    </style>\n'

    if align not in ('center', 'left', 'right'):
        align = 'center'

    BASE_CSS = f"""    <style>
        html {{
            scroll-behavior: smooth;
            -webkit-text-size-adjust: 100%;
        }}
        body {{
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            line-height: 1.6;
            font-size: clamp(1rem, 0.9rem + 0.5vw, 1.125rem);
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        body.align-left {{ margin: 0; }}
        body.align-right {{ margin: 0 0 0 auto; }}
        .text-align-left {{ text-align: left; }}
        .text-align-center {{ text-align: center; }}
        .text-align-right {{ text-align: right; }}
        img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
        }}
        pre {{
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }}
        code {{
            word-break: break-word;
        }}
        blockquote {{
            border-left: 4px solid currentColor;
            padding-left: 1rem;
            margin-left: 0;
            opacity: 0.9;
        }}
        table {{
            display: block;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            max-width: 100%;
        }}
        /* Alerts */
        .owomd-alert {{
            margin: 1.5rem 0;
            padding: 1rem;
            border-radius: 12px;
            border: 2px solid;
            border-left-width: 6px;
        }}
        .owomd-alert-title {{
            font-weight: bold;
            margin-bottom: 0.5rem;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .owomd-alert-content > *:first-child {{ margin-top: 0; }}
        .owomd-alert-content > *:last-child {{ margin-bottom: 0; }}

        .owomd-alert-note {{ border-color: #a78bfa; background-color: rgba(167, 139, 250, 0.1); }}
        .owomd-alert-note .owomd-alert-title {{ color: #a78bfa; }}

        .owomd-alert-tip {{ border-color: #34d399; background-color: rgba(52, 211, 153, 0.1); }}
        .owomd-alert-tip .owomd-alert-title {{ color: #34d399; }}

        .owomd-alert-important {{ border-color: #f472b6; background-color: rgba(244, 114, 182, 0.1); }}
        .owomd-alert-important .owomd-alert-title {{ color: #f472b6; }}

        .owomd-alert-warning {{ border-color: #fbbf24; background-color: rgba(251, 191, 36, 0.1); }}
        .owomd-alert-warning .owomd-alert-title {{ color: #fbbf24; }}

        .owomd-alert-caution {{ border-color: #f87171; background-color: rgba(248, 113, 113, 0.1); }}
        .owomd-alert-caution .owomd-alert-title {{ color: #f87171; }}

        /* Aesthetic defaults in case theme is missing something :3 */
        :root {{
            color-scheme: dark light;
        }}

        /* Responsive: mobile adjustments */
        @media (max-width: 600px) {{
            body {{
                padding: 1rem;
                font-size: 1rem;
            }}
            .owomd-alert {{
                padding: 0.75rem;
                margin: 1rem 0;
            }}
            pre {{
                padding: 0.75rem;
                font-size: 0.875rem;
            }}
            h1 {{ font-size: 1.75rem; }}
            h2 {{ font-size: 1.4rem; }}
            h3 {{ font-size: 1.15rem; }}
        }}
        @media (max-width: 400px) {{
            body {{
                padding: 0.75rem;
            }}
        }}
    </style>"""

    final_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
{head_tags}{css_links_html}{custom_css_html}{gradient_css}{BASE_CSS}
</head>
<body class="owomd-content align-{align}">
{html_output}</body>
</html>"""

    if '\x00' in final_html:
        raise OwomdError("Null byte found in input.")

    return final_html

# Server mode implementation :3c
class OwomdHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Parse query string :3
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        # Route / to index.md.owo automatically :3c
        if path == '/' or path == '':
            path = '/index.md.owo'
            
        # Check if requesting a template :3
        if path.endswith('.md.owo'):
            # Translate path securely to local file system :3c
            local_path = self.translate_path(path)
            
            if not os.path.exists(local_path):
                self.send_error(404, f"File not found: {path} :3")
                return
                
            # Parse query parameters :3
            query_params = urllib.parse.parse_qs(parsed_url.query)
            placeholder_data = {}
            
            # Load from --data file natively if it exists :3
            data_file = getattr(self.server, 'data_file', None)
            if data_file and os.path.exists(data_file):
                try:
                    with open(data_file, 'r', encoding='utf-8') as df:
                        placeholder_data = json.load(df)
                except Exception as e:
                    self.send_error(500, f"Error loading data file: {e} :3")
                    return
            
            if 'data' in query_params:
                try:
                    query_data = json.loads(query_params['data'][0])
                    if not isinstance(query_data, dict):
                        self.send_error(400, "Bad Request: data must be a JSON object :3")
                        return
                    placeholder_data.update(query_data)
                except json.JSONDecodeError:
                    self.send_error(400, "Bad Request: Invalid JSON in data parameter :3")
                    return
            
            try:
                with open(local_path, 'r', encoding='utf-8') as f:
                    template_text = f.read()
                    
                output = process_document(template_text, placeholder_data)
                
                # Send success response :3c
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(output.encode('utf-8'))
            except OwomdError as e:
                self.send_error(500, f"Owomd Evaluation Error: {e} :3")
            except Exception as e:
                self.send_error(500, f"Internal Server Error: {e} :3")
        else:
            # Fallback to serving normal static files :3
            super().do_GET()

def start_server(directory, port, data_file=None):
    os.chdir(directory)
    handler = OwomdHTTPRequestHandler
    
    # Use ThreadingHTTPServer for concurrent production readiness! :3c
    if hasattr(http.server, 'ThreadingHTTPServer'):
        server_class = http.server.ThreadingHTTPServer
    else:
        server_class = socketserver.TCPServer
        server_class.allow_reuse_address = True
        
    with server_class(("", port), handler) as httpd:
        httpd.data_file = data_file
        print(f"Serving at http://localhost:{port} :3c")
        if data_file:
            print(f"Loaded JSON data from {data_file} :3")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server... :3")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  ./owomd <template_path> [--force-stdin-read]")
        print("  ./owomd serve [directory] [--port 8000] [--data data.json]")
        sys.exit(1)
        
    command = sys.argv[1]
    
    if command == "serve":
        directory = "."
        port = 8000
        data_file = None
        
        # Parse serve args :3
        args = sys.argv[2:]
        if args and not args[0].startswith("--"):
            directory = args[0]
            args = args[1:]
            
        if "--port" in args:
            try:
                idx = args.index("--port")
                port = int(args[idx + 1])
            except (ValueError, IndexError):
                print("Error: Invalid port specified :3")
                sys.exit(1)

        if "--data" in args:
            try:
                idx = args.index("--data")
                data_file = args[idx + 1]
            except IndexError:
                print("Error: No data file specified after --data :3")
                sys.exit(1)
                
        if not os.path.isdir(directory):
            print(f"Error: Directory not found: {directory} :3")
            sys.exit(1)
            
        start_server(directory, port, data_file)
    else:
        # Standard file compilation mode :3c
        template_path = sys.argv[1]
        force_stdin = "--force-stdin-read" in sys.argv
        
        if not os.path.exists(template_path):
            print(f"Error: Template file not found: {template_path} :3")
            sys.exit(1)

        sys.stdin = os.fdopen(sys.stdin.fileno(), 'r', encoding='utf-8', closefd=False)
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)
            
        with open(template_path, 'r', encoding='utf-8') as f:
            template_text = f.read()
            
        placeholder_data = {}
        if not sys.stdin.isatty() or force_stdin:
            stdin_content = sys.stdin.read().strip()
            if stdin_content:
                try:
                    placeholder_data = json.loads(stdin_content)
                except json.JSONDecodeError:
                    print("Error: Invalid JSON provided in stdin :3")
                    sys.exit(1)
                    
        if not isinstance(placeholder_data, dict):
            print("Error: The top level of the placeholder must be a map :3")
            sys.exit(1)
            
        try:
            output = process_document(template_text, placeholder_data)
            sys.stdout.write(output)
        except OwomdError as e:
            print(f"! {e}")
            sys.exit(1)
        except Exception as e:
            print(f"! Unexpected error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
