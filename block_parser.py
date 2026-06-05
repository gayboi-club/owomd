import re

def parse_blocks(lines, start_line_num=1):
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        line_num = start_line_num + i

        # Iterator
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

        # Code block
        m = re.match(r'^```(.*)$', line)
        if m:
            lang_part = m.group(1).strip()
            templating = '+templating' in lang_part
            lang = lang_part.replace('+templating', '').strip()
            
            body = []
            j = i + 1
            while j < len(lines):
                if lines[j].strip().startswith('```'):
                    # End block :3c
                    break
                body.append(lines[j])
                j += 1
                
            blocks.append(('codeblock', lang, templating, body))
            i = j + 1
            continue

        # Quote
        if line.startswith('>'):
            # Collect consecutive quotes :3c
            quote_lines = []
            j = i
            while j < len(lines) and lines[j].startswith('>'):
                ql = lines[j][1:]
                if ql.startswith(' '):
                    ql = ql[1:]
                quote_lines.append(ql)
                j += 1
            blocks.append(('quote', parse_blocks(quote_lines, start_line_num + i)))
            i = j
            continue

        # Header
        m = re.match(r'^(\#{1,6})\s+(\S.*)$', line)
        if m:
            blocks.append(('header', len(m.group(1)), m.group(2), line_num))
            i += 1
            continue

        # List (Unordered)
        if line.startswith('- '):
            # Collect list item :3c
            blocks.append(('ul_item', line[2:], line_num))
            i += 1
            continue

        # List (Ordered)
        m = re.match(r'^\d+\.\s+(.*)$', line)
        if m:
            blocks.append(('ol_item', m.group(1), line_num))
            i += 1
            continue

        # Empty line
        if line.strip() == '':
            i += 1
            continue

        # Paragraph
        blocks.append(('paragraph', line, line_num))
        i += 1

    # Group list items
    grouped_blocks = []
    curr_list = None
    list_type = None

    for b in blocks:
        if b[0] == 'ul_item':
            if list_type != 'ul':
                if curr_list:
                    grouped_blocks.append((list_type, curr_list))
                curr_list = []
                list_type = 'ul'
            curr_list.append(b)
        elif b[0] == 'ol_item':
            if list_type != 'ol':
                if curr_list:
                    grouped_blocks.append((list_type, curr_list))
                curr_list = []
                list_type = 'ol'
            curr_list.append(b)
        else:
            if curr_list:
                grouped_blocks.append((list_type, curr_list))
                curr_list = None
                list_type = None
            grouped_blocks.append(b)

    if curr_list:
        grouped_blocks.append((list_type, curr_list))

    return grouped_blocks
